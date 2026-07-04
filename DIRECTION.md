# Direction: Parity-Carry Traversal — kill idx reconstruction on shallow rounds

> **REVIEW CORRECTION (verified against `reference_kernel2` traces, 256 elem × 16 rounds):
> the original identity as stated is FALSE and its Day-1 script would have falsely killed
> the direction.** The claim "idx's low bits ARE the accumulated parity bits" fails on
> 1536/1536 shallow-round samples. The true relationship involves an offset: with the
> parity accumulator `p` (`p ← 2p + rem`, reset to 0 after the bottom wrap), the verified
> invariant is
>
> ```
> idx == 2^d − 1 + p        (0 violations in 4096 round-element samples)
> ```
>
> so idx's low d bits are `(p − 1) mod 2^d`, which differs from `p` by a **borrow chain**:
> at depth 1 the bit is the *complement* of the parity; at depth 2/3 higher bits are
> XNOR-like mixtures (e.g. d2 bit1 = ¬(rem0 XOR rem1)), NOT individual parity bits.
> Feeding raw parity bits to the existing vselect conditions is therefore wrong.
> **The direction survives in a corrected form:** key the vselect tournament on the parity
> bits *directly* and re-permute the broadcast table so position `p` holds
> `tree[2^d − 1 + p]` — the mapping parity-bits→node is still a bijection, so no extract
> or reconstruction is needed at all. Details in §3 (rewritten).

## 1. Direction name + one-line thesis

**Parity-carry traversal (corrected).** The hash is nonlinear, so fusing rounds or
precomputing early hashes is algebraically impossible — but the depth cycle means the node
at a shallow round is fully determined by the recent branch parities: `node = tree[2^d−1+p]`
where `p` is the accumulated parity value. Key the node-select tournament on the individual
parity vectors (`rem = val%2`, already computed every round) against a **re-permuted
broadcast table**, instead of reconstructing the full `idx` integer and extracting its low
bits. This deletes the `&`-extract valu ops (and, where the successor never reads `idx`,
the `i2p1` muladd) from the **binding valu floor**, lowering the floor itself rather than
merely relocating work.

---

## 2. Why this could beat 1230 (quantitative, tied to verified floors)

Measured engine profile at the current 1230-cycle build (verified by counting slots in
`kb.instrs`):

```
valu:  7055 ops / 6 = 1175.8   <-- NOW THE BINDING SINGLE-ENGINE FLOOR
alu:  13456 ops /12 = 1121.3
load:  2196 ops / 2 = 1098.0
flow:   736 ops / 1 =  736.0   (60% idle -- 494 slot-equiv of headroom)
store:   32 ops / 2 =   16.0
combined alu+valu true floor ~= 1174   (from OPTIMIZATION_NOTES.md §2)
```

The prior tail-rebalance work pushed so much XOR onto the ALU engine that **valu is now the
tightest engine at 1175.8**, essentially equal to the combined floor of 1174. The notes'
conclusion ("1230 near this scheduler's limit; the gap is windup/drain packing") is true *given
the current op set*. This direction attacks a different axis: **it changes the op set**, so it
is not blocked by "the scheduler is already near-perfect (only 17 pure stalls)."

**What is on the table (verified idx-set structure, `n_nodes=2047`, `h1=11`):**

```
round  0 d0: idx={0}            round  8 d8: gather
round  1 d1: idx in {1,2}       round  9 d9: gather
round  2 d2: idx in {3..6}      round 10 d10: gather (bottom -> wrap to 0)
round  3 d3: idx in {7..14}     round 11 d0: idx={0}      <-- cycle repeats
round  4 d4: gather (>=15)      round 12 d1
round  5 d5: gather             round 13 d2
round  6 d6: gather             round 14 d3
round  7 d7: gather             round 15 d4: gather (idx update skipped)
```

The shallow, non-gather rounds are exactly `{0,1,2,3, 11,12,13,14}`. On these the node is
picked by a `vselect` tournament keyed on the **low bits of idx**. The corrected algebra
(verified, see header):

- After a wrap-to-0 (rounds 0 and 11), `idx=0`, `p=0`. Then with `p ← 2p + rem` each round,
  `idx_{depth d} = 2^d − 1 + p` exactly (0/4096 trace violations). Examples:
  `idx_{d1} = 1 + rem0` → low bit = `¬rem0` (complement, NOT `rem0`);
  `idx_{d2} = 3 + 2·rem0 + rem1` → `idx&1 = ¬rem1`, `(idx>>1)&1 = ¬(rem0 XOR rem1)`.
- So idx's low bits are borrow-mixed parities — you cannot substitute parity bits into the
  *existing* conditions. But the node is a pure function of `p`: `node = tree[2^d−1+p]`.
  **Re-permute the broadcast table to be indexed by `p`'s bits** (i.e. by the raw parity
  vectors `rem_{r-1}, rem_{r-2}, rem_{r-3}`, all already computed as `val%2` in the traverse)
  and the `&`-extracts plus the `i2p1 = 2*idx+1` muladd that rebuild `idx` purely to
  re-derive select conditions become redundant on the shallow rounds.

**Op-count budget (candidate removals):**

- `&`-extract valu ops on shallow-round node-select:
  depth1 = 1 `&`, depth2 = 2 (`&`,`<`... the `&` is 1), depth3 = 3 `&`. Over rounds
  `{1,12}`(d1), `{2,13}`(d2), `{3,14}`(d3): `(1+2+3) * 2 * 32 = 384` valu ops.
- `i2p1` traverse muladd on shallow non-final rounds that feed a shallow next round:
  additional tens–low-hundreds of valu ops depending on how much of the idx integer we can
  stop materializing (see §5 — the gather rounds still need a real `idx`, so this is partial).

At 6 valu-ops-removed ≈ 1 cycle off the 1175.8 floor:
- Removing just the 384 `&`-extracts → floor drops ~64 cycles (ceiling of this lane, if
  fully realizable and if the tails can still be packed).
- Realistic: partial realization + scheduler packing losses → **~15-60 cycles**, landing
  1170–1215.

This is the only lane identified that lowers the *binding* floor rather than rebalancing across
it. Rebalance (proven: head/tail combine placement) is exhausted; op-count reduction is not.

---

## 3. Mechanism: exactly what changes in `perf_takehome.py`

All edits are in `KernelBuilder._emit_vec_round` (lines 321–449) and its per-vector state
(`vs` entries built at lines 618–632). No scheduler change; correctness is defined by final
`mem[inp_values_p:...]` matching `reference_kernel2`, and `idx` is NOT checked (confirmed in
`do_kernel_test`, lines 776–783, and by the `skip_idx_update` path already in the code).

### 3.1 Keep the recent `rem` vectors alive instead of an accumulator (CORRECTED)

A packed `pbits` accumulator is useless for the vselects: the conditions need *individual*
bits, and extracting a bit from a packed accumulator costs the same `&` op we are trying to
delete. Instead, keep the last up-to-3 **raw parity vectors** alive. `rem = val % 2` is
already computed every round into the recycled `addr` temp (line 432); redirect it into a
small ring of dedicated vectors:

```python
entry["rem0"] = self.vec(f"{p}_rem0")   # parity of round r-1 (newest)
entry["rem1"] = self.vec(f"{p}_rem1")   # parity of round r-2
entry["rem2"] = self.vec(f"{p}_rem2")   # parity of round r-3 (only live rounds 2-3, 13-14)
```

Scratch budget: +3 vec (24 words) × K_VEC=32 = **768 words naive — does NOT fit** (current
use 1471/1536, 65 free). This forces overlap: the rem history is only consumed during the
shallow window (rounds 0–3 and 11–14), during which the gather-only temps are dead; and
`rem0` can simply *be* the existing `rem` write target. A workable layout: 1 extra vec per
vector (+256 words) with the other two slots overlapping `node`/`addr` lifetimes — this is
the fiddliest part of the direction and must be planned before coding (see §5 risk 4).

### 3.2 Zero-cost maintenance

No shift-register op is needed at all: "maintenance" is just *writing this round's `rem`
into a different slot of the ring* (rotate the role of the 3 vectors by round index at
emission time — a compile-time renaming, zero runtime ops). This is strictly cheaper than
the original draft's `pbits = 2*pbits + rem` muladd (which would have cost 1 valu/round).

### 3.3 Re-permute the broadcast tables and key the vselects on raw parities (CORRECTED)

The existing conditions (`idx&1`, `idx&2`, `idx&4`, `4<idx`) CANNOT be replaced by parity
bits one-for-one (borrow mixing — see header). Instead, use `node = tree[2^d − 1 + p]`
with `p = Σ 2^k·rem_{d-1-k}` and re-order the broadcast table by `p`:

- **depth 1** (line 336): today `mask = idx&1` selects `nb1` vs `nb2`. In parity space
  `p = rem0`, node = `tree[1 + p]`: emit `vselect(node, rem0, nb2, nb1)` (branches swapped
  vs. the idx&1 version, since idx&1 = ¬rem0). The `&` (1 valu) is **deleted**.
- **depth 2** (lines 347–357): node = `tree[3 + p]`, `p = 2·rem0 + rem1 ∈ {0..3}`.
  Tournament: level 1 on `rem1` (newest), level 2 on `rem0`, over broadcasts ordered
  `tree[3],tree[4],tree[5],tree[6]` indexed by `p`. Deletes the `&` and the `<` (2 valu).
- **depth 3** (lines 369–395): node = `tree[7 + p]`, `p = 4·rem0 + 2·rem1 + rem2 ∈ {0..7}`.
  Re-order the `d3_*` broadcast permutation (`d3_order`, line 590) so position `p` holds
  `tree[7+p]`, and run the same 7-vselect tournament keyed on `rem2/rem1/rem0`. Deletes
  all 3 `&` extracts (3 valu per vec-round).

The vselect tournament flow ops themselves are unchanged — they stay on the **flow**
engine, which has ~494 slots of headroom. The broadcast tables are setup-only re-orderings
(zero new runtime ops).

### 3.4 Keep the full `idx` integer ONLY where needed

The gather rounds (depth≥4, lines 396–400) and the wrap check (`depth == fh`, lines 445–449)
need the real `idx`. So the `i2p1` muladd + `idx = i2p1 + rem` (lines 440–441) must still run on
any round whose **next** round is a gather (i.e. we need `idx` materialized entering depth 3→4)
and on the descent generally. The clean rule:

- Maintain `pbits` on every round (cheap, 1 op).
- On rounds `1,2,3,12,13` (shallow, next round also shallow or the current select is shallow):
  drive node-select from `pbits`/`rem`, and **skip the `&`-extracts**.
- On round 3 (→ round 4 gather) and round 14 (→ round 15 gather): we still need the full `idx`
  to compute the gather address at round 4/15, so keep the `idx` reconstruction there. But the
  *node-select at round 3 itself* still uses `pbits` bits, so its 3 `&`-extracts are still
  removable even though `idx` is rebuilt for the next round's address.

This makes the removable set the **node-select `&`-extracts on rounds {1,2,3,12,13,14}**, robust
regardless of whether `idx` must persist. That is the 384-op figure. The `i2p1` removals are a
secondary, smaller win only on rounds whose successor never needs `idx` — audit case-by-case.

### 3.5 Correctness anchor

The substitution is NOT bit-identical at the condition level (idx low bits ≠ parity bits);
it is *node-identical* via the invariant `node = tree[2^d − 1 + p]` and the re-permuted
tables. The invariant is verified on reference traces (0/4096 violations), but every table
permutation and branch order must be validated against `reference_kernel2` (bit-exact) —
not by reasoning. A single swapped branch produces wrong nodes on ~half the lanes.

---

## 4. Day-1 experiment (smallest thing to validate or kill fast)

**Goal: prove the corrected invariant `idx == 2^d − 1 + p` at every round, in the real
trace, before touching op emission.** This is a pure correctness/structure check with zero
scheduling risk.

> The original draft's Step A asserted `idx & mask == pbits & mask` — that assertion
> **fails on 1536/1536 shallow-round samples** (the bits are borrow-mixed, see header) and
> would have falsely killed a viable direction. Use the corrected check below (already run
> once during review: **passes, 0/4096 violations**).

Step A — dump the trace and confirm the corrected algebra on real data:

```bash
cd /Users/haiyan-mini/Agent4Kernel/vliw
python3 - <<'PY'
import random
from problem import Tree, Input, build_mem_image, reference_kernel2
random.seed(7)
f = Tree.generate(10); inp = Input.generate(f, 256, 16)
mem = build_mem_image(f, inp)
tr = {}
for _ in reference_kernel2(mem, tr): pass
h1 = 11
bad = 0
for i in range(256):
    p = 0
    for r in range(16):
        d = r % h1
        idx = tr[(r, i, "idx")]
        if idx != (1 << d) - 1 + p: bad += 1
        rem = tr[(r, i, "hashed_val")] & 1
        p = 0 if d == 10 else (2 * p + rem)   # reset after the bottom wrap
print("invariant idx == 2^d-1+p violations:", bad, "/ 4096")   # expect 0
PY
```

If this prints 0, the algebraic core is proven on real data and the corrected lane
(§3.3 table re-permutation) is viable. If it fails, the wrap/reset logic is wrong — cheap
kill.

Step B — implement only the **depth-3 `&`-extract removal** (the biggest single chunk: 192 valu
ops), leaving everything else identical, then measure:

```bash
cd /Users/haiyan-mini/Agent4Kernel/vliw
python3 -c "from perf_takehome import do_kernel_test; do_kernel_test(10,16,256)"
# reads 'CYCLES: <n>' -- baseline is 1230. Also confirm it prints no assertion error.
# Full correctness gate:
python tests/submission_tests.py    # must print OK and CYCLES: <n>
```

Because `cycles == len(kb.instrs)` and is data-independent (OPTIMIZATION_NOTES §1.1), one run is
authoritative. Decision rule: if removing 192 valu ops does **not** move cycles below ~1225,
the valu floor is being masked by scheduler packing in the tails and the full lane will
underdeliver — deprioritize. If it drops toward 1215 or below, proceed to depth-1/2 removals and
the `i2p1` audit.

---

## 5. Risks & likely failure modes (honest)

1. **The floor is not the wall.** The notes show the middle `[200-1000]` is jointly alu+valu
   saturated but the gap over 1174 lives in windup/drain packing (only 17 pure stalls). If the
   removed valu ops were all in the *middle* (fully packed) region, deleting them lowers the
   floor and should help; but if they were being co-scheduled into otherwise-idle valu slots in
   the tails, removing them yields nothing. **Likely partial:** shallow rounds `{1,2,3}` are
   early (windup) and `{12,13,14}` are late-ish — a mix. Day-1 Step B measures this directly.

2. **Parity update reintroduces valu ops.** Each `pbits` maintenance is ~1 valu op/round; if we
   pay it on all 16 rounds but only save on 6, the net could be small or negative.
   **RESOLVED BY REVIEW:** the corrected mechanism (§3.1-3.2) needs no accumulator and no
   maintenance op at all — the ring of raw `rem` vectors is rotated by compile-time renaming
   (zero runtime ops). This risk is retired; the residual cost is scratch, not ops (risk 4).

3. **`idx` still needed for gathers.** We cannot stop computing `idx` entirely — depth≥4
   rounds gather at `fvp+idx`. So the `i2p1` muladd removal is only valid on the narrow set
   of rounds whose successor never reads `idx`. Over-aggressive removal breaks the gather
   addresses → wrong `val` → correctness failure. The *robust* win is confined to the
   `&`-extracts (384 ops); the muladd win is a bonus requiring careful per-round auditing.
   Note: review found round 10's entire idx update (traverse + wrap) is dead code
   independent of this direction — see `11-dead-code-idx`, which should land first and
   shrinks this direction's remaining muladd surface.

4. **Scratch pressure — now the PRIMARY risk.** Three raw parity vectors per vector = 768
   words naive, but only **65 words are free** (measured: 1471/1536). The design must
   overlap the rem ring with temps that are dead during the shallow window (`node`/`addr`
   between rounds, gather-only temps), or accept keeping only 1-2 history vectors and
   retaining one `&`-extract at depth 3. This is a live-range puzzle and the most likely
   place the direction stalls; plan the layout on paper before coding.

5. **Bit-order / wrap subtlety.** After wrap at round 10 (idx→0), the parity history must reset
   for the depth-cycle restart at round 11. Day-1 Step A tests exactly this across the wrap
   boundary; if the assertion trips at round 11+, the reset logic needs care.

6. **The prompt's headline idea (round fusion / early-hash precompute) is genuinely dead** and
   must not be pursued: the hash is nonlinear (`xor` does not distribute over `+`/`*`/`<<`), so
   two fused rounds still require two full hashes, and per-element `val` inputs are in mem
   (not build-time known), so no early hash can be precomputed at setup. Verified. This doc
   redirects the lane to the one *live* consequence of the depth-cycle structure: parity-carry.

---

## 6. Expected payoff + confidence + effort

- **Optimistic (low):** ~1150 — full removal of 384 `&`-extracts (−64 floor) partially realized
  plus a few `i2p1` removals, minus parity-maintenance and packing losses.
- **Likely (high):** ~1215–1225 — depth-3 removal lands a real but modest cut; depth-1/2 and
  muladd removals are marginal after parity-maintenance overhead.
- **Confidence it beats 1230 at all: medium.** The corrected algebra is proven on reference
  traces (0/4096 violations — review already ran Step A), so ops *can* be removed correctly;
  the uncertainty is (a) whether the scratch live-range puzzle (risk 4) admits a full 3-vector
  rem ring, and (b) whether the removed ops sat in packed regions (real cycle win) vs. idle
  tails (no win). Only Step B resolves (b).
- **Effort: 2–4 days.** Day 1: algebra proof + depth-3 removal + measure (kill/continue gate).
  Day 2: depth-1/2 removals, parity-maintenance folding, scratch layout. Day 3–4: `i2p1`
  per-round audit, re-tune the existing head/tail combine sweep (§4.1 of notes) against the new
  op profile since the binding engine mix will have shifted, and full correctness sweep.

---

## 7. Dependencies / prerequisites

- **No external libraries.** Pure edits to `perf_takehome.py` (`_emit_vec_round` lines 321–449;
  per-vector scratch lines 618–632). Scheduler (`class Scheduler`) untouched.
- **Scratch budget:** confirm headroom before adding `pbits`. Check with:
  ```bash
  python3 -c "from perf_takehome import KernelBuilder; kb=KernelBuilder(); kb.build_kernel(10,2047,256,16); print('scratch used:', kb.scratch_ptr, '/', 1536)"
  ```
  If the margin is < 256 words, plan to overlap `pbits` with the freed `addr`/`node` temps.
- **Re-run the head/tail combine sweep afterward.** The current `_combine_head=10 /
  _combine_tail=100` (lines 233–234) were tuned to the *old* op profile. Removing valu ops
  shifts which engine binds in the tails, so the optimal head/tail will move. Budget one grid
  sweep (the notes report ~64+25 builds) as a dependent follow-up — do NOT report a final number
  before re-tuning it.
- **Correctness gate (mandatory, every iteration):**
  ```bash
  git diff origin/main -- tests/     # MUST be empty (never touch tests/, incl frozen_problem.py)
  python tests/submission_tests.py   # MUST print OK + CYCLES
  ```
  Because the program is data-independent, cycle count is exact from one build, but correctness
  must be validated on the unseeded random inputs that `submission_tests.py` uses.
- **Prerequisite reading for the next engineer:** OPTIMIZATION_NOTES.md §2 (why valu, not alu,
  is now the true floor) and §3 (why the middle is unbeatable and the tails are the packing
  frontier) — both determine whether a removed op converts to a saved cycle.
# Direction: Parity-Carry Traversal — kill idx reconstruction on shallow rounds

## 1. Direction name + one-line thesis

**Parity-carry traversal.** The hash is nonlinear, so fusing rounds or precomputing early
hashes is algebraically impossible — but the depth cycle means the node-select conditions on
shallow rounds (`idx&1`, `idx&2`, `idx&4`) are *exactly* the recent branch-parity bits that
`val % 2` already emits. Carry the parity bits directly instead of reconstructing the full
`idx` integer and re-extracting its low bits, deleting the `i2p1` muladd and the `&`-extract
ops on the 6 shallow non-final rounds. This removes ops from the **binding valu floor**, which
lowers the floor itself rather than merely relocating work.

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
picked by a `vselect` tournament keyed on the **low bits of idx**. Those low bits are precisely
the parity choices (`rem = val%2`) accumulated over the last few rounds:

- After a wrap-to-0 (rounds 0 and 11), `idx=0`. Then
  `idx_{d1} = 1 + rem0` → low bit = `rem0`.
  `idx_{d2} = 2*idx_{d1} + 1 + rem1` → `idx&1 = rem1`, `(idx>>1)&1 = rem0`.
  `idx_{d3}` low 3 bits = `(rem0, rem1, rem2)`.
- So the vselect conditions `idx&1 / idx&2 / idx&4` at depth `d` are just the last `d` parity
  bits, in a fixed order. **We already compute `rem = val%2` every round** (the traverse step).
  The `&`-extracts and the `i2p1 = 2*idx+1` muladd that rebuild `idx` purely to re-derive those
  same bits are redundant on the shallow rounds.

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

### 3.1 Add a per-vector parity register `pbits`

In the per-vector scratch loop (lines 618–632), add one vector `pbits` per vector:

```python
entry["pbits"] = self.vec(f"{p}_pbits")   # holds accumulated recent parity bits
```

Scratch budget: +1 vec (8 words) × K_VEC=32 = 256 words. Current build uses well under
`SCRATCH_SIZE=1536`; verify headroom on Day 1 (see §7). If tight, `pbits` can overlap the
`addr` scratch on shallow rounds since `addr` is a scratch temp freed after node-select.

### 3.2 Maintain `pbits` cheaply from the `rem` we already compute

Today the traverse computes `rem = val % 2` (line 432) then rebuilds `idx`. Change the shallow
rounds so that instead of (or in addition to) reconstructing `idx`, we shift the new parity in:

```
pbits_new = (pbits << 1) | rem      # low bit = most recent parity
```

`<<` and `|` are elementwise `valu`/`alu` ops. Crucially, `rem` (`val%2`) is *already* emitted,
so the marginal cost is one `<<`+`|` (or a single `multiply_add(pbits,2, rem)` — 1 valu op)
per shallow round. We are trading: **delete** `i2p1` muladd (1 valu) + node-select `&`-extracts
(1–3 valu) → **add** one parity-update (1 valu). Net negative on shallow rounds.

### 3.3 Rewrite shallow-round node-select to key off `pbits` directly

In `_emit_vec_round`, the `depth == 1/2/3` branches (lines 331–395) currently do
`self.v_alu("&", addr, idx, one_v)` etc. Replace with reads of `pbits`:

- **depth 1** (line 336): condition is `pbits & 1` (the single most-recent parity). If we keep
  `pbits`'s low bit as that parity, the `&` may still be needed — but we can arrange the
  vselect to read `pbits` bit0 without a separate extract if we instead maintain a dedicated
  1-bit `rem` vector (which is `val%2`, already computed) and feed it straight to `vselect`.
  Net: the depth-1 `&` (line 336) is *deleted* — the vselect condition becomes the existing
  `rem` vector.
- **depth 2** (lines 347–357): conditions `odd = idx&1` and `hi = (4<idx)`. `odd` = the newest
  parity (`rem` of the previous round) — reuse it, delete the `&`. `hi` distinguishes
  idx∈{5,6} from {3,4}, which is the *second* parity bit — read `pbits` bit1 (one extract, or
  keep the two parities in two 1-bit vectors to avoid it). Net: delete 1–2 valu.
- **depth 3** (lines 369–395): three conditions `b0,b1,b2` = the three most recent parities.
  These are exactly `pbits` bits 0/1/2. Keep three 1-bit parity vectors (`rem` at rounds r-1,
  r-2, r-3) and feed them to the vselect tournament directly. Net: delete all 3 `&` extracts
  (lines 369, 384, 392) → 3 valu removed per depth-3 (vec,round).

The vselect tournament flow ops themselves (lines 371–395) are unchanged — they stay on the
**flow** engine, which has 494 slots of headroom, so absorbing any extra select is free.

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

`pbits`/`rem` must reproduce the exact vselect condition each depth uses today. Because the
existing code already *works* using `idx & mask`, and `idx`'s low bits provably equal the
accumulated parities (§2), the substitution is bit-identical. Validate against
`reference_kernel2` (which is bit-exact) — not by reasoning.

---

## 4. Day-1 experiment (smallest thing to validate or kill fast)

**Goal: prove the parity-bits equal the idx low-bits at every shallow round, in the real trace,
before touching op emission.** This is a pure correctness/structure check with zero scheduling
risk.

Step A — dump the trace and confirm the algebra on real data:

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
# For each element, rebuild pbits from rem = val%2 and check it matches idx low bits
bad = 0
for i in range(256):
    pbits = 0
    for r in range(16):
        d = r % h1
        idx = tr[(r, i, "idx")]
        if d == 1: assert (idx & 1) == (pbits & 1), (r,i)
        if d == 2:
            assert (idx & 1) == (pbits & 1) and ((idx>>1)&1) == ((pbits>>1)&1), (r,i)
        if d == 3:
            for b in range(3):
                assert ((idx>>b)&1) == ((pbits>>b)&1), (r,i,b)
        rem = tr[(r, i, "hashed_val")] % 2
        pbits = (pbits << 1) | rem
print("parity-carry algebra holds for all 256 elements x shallow rounds")
PY
```

If this asserts cleanly, the algebraic core is proven on real data and the whole lane is viable.
If it fails, the direction is **dead on Day 1** (the bit ordering / wrap interaction is wrong)
— cheap kill.

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
   pay it on all 16 rounds but only save on 6, the net could be small or negative. Mitigation:
   only maintain `pbits` where consumed (rounds feeding a shallow select), and fold the update
   into the `rem` computation (`rem` already exists) so the marginal op is `multiply_add(pbits,
   2, rem)` = 1 valu replacing a `<<`+`|`.

3. **`idx` still needed for gathers/wrap.** We cannot stop computing `idx` entirely — depth≥4
   rounds gather at `fvp+idx`, and round 10 wraps. So the `i2p1` muladd removal is only valid on
   the narrow set of rounds whose successor never reads `idx`. Over-aggressive removal breaks
   the gather addresses → wrong `val` → correctness failure. The *robust* win is confined to the
   `&`-extracts (384 ops); the muladd win is a bonus requiring careful per-round auditing.

4. **Scratch pressure.** +256 words for `pbits` (or three 1-bit parity vectors ×32 = up to 768
   words if done naively). Must confirm `scratch_ptr <= 1536`. Mitigation: reuse the freed
   `addr` temp, or store parities packed in one `pbits` vector (8 words/vec) and extract with
   `>>`+`&` on flow/alu (idle engines), not valu.

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
- **Confidence it beats 1230 at all: medium.** The algebra is provable (Day-1 Step A is a
  near-certain pass), so ops *will* be removed correctly; the uncertainty is entirely whether
  those ops sat in packed regions (real cycle win) vs. idle tails (no win). This is exactly what
  the notes flag as the crux, and only Step B resolves it.
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
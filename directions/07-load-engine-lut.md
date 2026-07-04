# Direction: LUT-offload to the LOAD engine

> **VERDICT: DEPRECATED (July 2026, self-refuted).** load floor (1066) below binding alu+valu
> (~1111). Gather-reduction marginal on 1208 graph. Archive only.

> Assigned lane: "Offload ALU work onto the idle LOAD engine (floor 1098, ~132 cycles of
> slack vs 1230). Precompute a partial hash LUT in memory at SETUP, then at runtime replace
> some ALU/valu hash work with a LUT load."
>
> **Verdict after Day-0 measurement: the direction AS LITERALLY STATED is REFUTED.** This
> document records exactly why (with numbers a fresh engineer can reproduce in one command),
> and then salvages the one quantitatively-defensible residual — a *gather-reduction* play on
> the depth>=4 node fetch — which is a different mechanism than "LUT the hash" but is the only
> way this lane touches the load floor. Read section 2 before spending a day on the naive idea.

All facts below were measured on the real builder at `forest_height=10, rounds=16, batch=256`
(the frozen test shape), not derived. Baseline reproduced: **1230 cycles**.

---

## 1. Direction name + one-line thesis

**LUT-offload to the LOAD engine.** Move hash (or node-fetch) work out of the ALU/valu
engines and into a memory table read by the load engine, exploiting the load engine's floor
of 1098 (132 cycles below the 1230 baseline).

**Thesis (post-measurement):** This cannot work as an ALU-offload, because (a) there is no
gather instruction — a data-indexed vector table read costs **8 scalar `load` ops**, not 1-2;
(b) the load engine is **already 100% saturated in the middle** [cycles 300-1050]; and (c) the
only hash sub-word that is cleanly LUT-able is the low half of the `<<` stages, which already
cost just one `multiply_add` — there is nothing to buy. The residual worth pursuing is a
*narrower* mechanism: shrink the 2048 mandatory node-gather loads so the load engine stops
being the middle-band wall, which is a genuine (if small) attack on floor 1098.

---

## 2. Why this could beat 1230 — and the three measurements that say it mostly can't

The lane brief asserts "the load engine is under-utilized outside gather rounds." **That is
false for this already-optimized kernel.** Here is the load-engine occupancy in 150-cycle
windows (reproduce with the Day-1 command in section 4):

```
[0-150]     load  67%     <- windup: genuine slack
[150-300]   load  97%
[300-450]   load 100%     ┐
[450-600]   load 100%     │
[600-750]   load 100%     │ MIDDLE BAND: load engine is SATURATED
[750-900]   load 100%     │ (750 of 1230 cycles at 100%)
[900-1050]  load 100%     ┘
[1050-1200] load  59%     ┐ drain: genuine slack
[1200-1230] load  40%     ┘
```

Total load ops = **2196** (floor 1098). Breakdown:
- `const` 82, `vload` 66 (idx/val blocks + tree setup), **scalar `load` 2048**.
- The 2048 scalar loads are **all** depth>=4 node gathers: gather rounds are r in
  {4,5,6,7,8,9,10,15} (depth = r%11), 8 rounds x 32 vectors x 8 lanes = **2048**. This is the
  minimum already: depths 0-3 were converted to vselect muxes (see `_emit_vec_round`
  depth 0/1/2/3 branches, `perf_takehome.py:325-395`).

**Consequence:** the ~132 cycles of load slack (2196/2=1098 floor vs 1230) does **not** sit in
an idle middle you can dump ALU work into. It sits in the *same windup [0-150] and drain
[1050-1230] tails* that OPTIMIZATION_NOTES.md section 4 already mined for idle *valu*. Any op you
move onto the load engine in the middle collides with a 100%-full engine and stalls.

### 2a. The killer: there is no gather instruction

A LUT indexed by a data value (e.g. `table[hash(a) & mask]`) needs 8 arbitrary addresses per
vector — one per lane. The ISA (`problem.py:269-286`) has only:
- `("load", dest, addr)` — one scalar word (1 load slot),
- `("vload", dest, addr)` — 8 **contiguous** words `mem[addr..addr+8]` (1 load slot),
- `("const", …)`.

There is **no** `("vgather", dest, idx_vec)`. So a vector LUT lookup = **8 scalar `load`
slots** = 4 cycles of load-engine occupancy per vector-lookup. This is exactly why the node
gather already costs 8 loads/vector.

Numerically: one hash stage replaced by a LUT over 32 vec x 16 rounds = 512 lookups x 8 =
**+4096 load ops**. New load total 2196+4096 = 6292 -> **load floor 3146**. A single LUT stage
blows past 1230 by ~1900 cycles on the load engine alone. **Dead.**

### 2b. The hash is not sub-word separable where it matters

`myhash` (`problem.py:449-464`) is 6 stages of `a = (a op1 K) op2 (a op3 s)`. The `>>` stages
(stage 1: `>>19`, stage 5: `>>16`) pull high input bits down into low output positions.
Measured: the low 8 and low 16 bits of the *full* hash depend on **all 32** input bits
(2000/2000 test inputs). So a "low-bits sub-word LUT of the whole hash" is impossible; you
cannot avoid indexing on all 32 bits.

Per-stage separability (measured over 3000 inputs each):

| stage | form | low-16 out depends only on low-16 in? |
|---|---|---|
| 0 | `+`/`<<12` | **YES** (separable) |
| 1 | `^`/`>>19` | NO (shift-down) |
| 2 | `+`/`<<5`  | **YES** |
| 3 | `^`/`<<9`  | **YES** |
| 4 | `+`/`<<3`  | **YES** |
| 5 | `^`/`>>16` | NO (shift-down) |

But even for a separable `<<` stage, **only the LOW output half is a clean 2^16 LUT**; the
HIGH output half depends on both input halves (measured 3000/3000) → needs a 2^32 index.
Worse: the four separable stages (0,2,4 and the `+` combine) are exactly the ones the kernel
*already folds into a single `multiply_add`* (`perf_takehome.py:419,423,425` +
`build_kernel` docstring: `a*(2^s+1)+K`). They cost **1 valu op**. There is no ALU work there
to offload. The expensive stages (1,3,5, the `^`-combines that cost 2 valu + 1 combine) are
either non-separable (`>>`) or, for stage 3 (`<<9`), only half-LUT-able while still needing
the high-half arithmetic — a strict loss vs. the current 3-op combine.

### 2c. What IS on the table (the salvage)

The only load-floor lever that survives is **reducing the 2048 mandatory node gathers**. Every
gather load removed frees a 100%-saturated middle-band slot. If you could cut the load floor
from 1098 toward ~1000, the middle band would stop being load-bound and the schedule could
tighten. Two concrete sub-mechanisms (both are gather-reduction, NOT hash-LUT):

- **(S1) Extend the vselect mux one level to depth 4** (idx in [15,30], 16 distinct nodes),
  eliminating 2 rounds x 32 x 8 = 512 gather loads. **BUT** a 16-way mux costs ~15 flow +
  4 valu per vector; 2 rounds x 32 x 15 = 960 flow ops added. Flow floor is currently 736
  (1 slot/cycle) → **+960 → flow floor 1696**. The flow engine (1 slot/cycle) is the wall that
  stops muxes past depth 3. **This is why OPTIMIZATION_NOTES.md found re-gather/deeper muxes
  dead.** S1 is dead for the same reason unless flow pressure is simultaneously cut.
- **(S2) Partial-node LUT via `vload` (contiguous, 1 slot).** This is the *only* LUT that
  respects the "no gather" constraint. It does not index by hash; it exploits tree structure.
  See section 3.

---

## 3. Mechanism: exactly what changes in `perf_takehome.py`

Because the hash-LUT is dead (2a/2b), the mechanism section describes **S2**, the only
LUT-shaped idea that (i) uses `vload` (contiguous, 1 load slot, no gather) and (ii) could
lower the load floor.

**Idea (S2): fold a subtree into a precomputed per-lane transform table at SETUP, so that a
depth-d gather round reads fewer than 8 loads/vector.** The tree values `mem[fvp+idx]` are
data (random per run), so you cannot precompute the *hash*; but the *addresses* are structural.
Concretely, the promising variant is a **"2-nodes-per-load" packing**: at setup (store engine
is 100% idle — 32/2 = 16 cycles used of thousands available, verified: store total = 32 ops),
build a contiguous scratch/mem region `pair[k] = f(tree[2k], tree[2k+1])` is NOT possible
(f depends on runtime idx parity), so instead:

- **S2a — gather-width halving by contiguous sibling `vload`:** at depth d, lanes whose idx
  differ only in the low bit are siblings and are **contiguous in memory** (`tree[2p+1]`,
  `tree[2p+2]`). If two lanes of a vector happen to be siblings you could `vload` a 8-wide
  block covering them. In practice idx across the 8 lanes of a vector are unrelated (different
  batch elements), so contiguity does not hold — **measure the actual idx spread before
  assuming** (Day-1). Expected: no exploitable contiguity → S2a likely dead.

- **S2b — depth-4-only structural LUT built at setup into contiguous scratch, read by
  `vload`+`vselect`:** depth 4 has only 16 distinct node values. Instead of a 16-way flow mux
  (S1, flow-bound) or 8 gathers, `vload` the 16 tree values into 2 contiguous vectors at setup
  (2 load slots, once), then select per-lane. But per-lane selection among 16 values with data
  indices still needs either flow muxes (flow-bound, dead per S1) or gather (load-bound).
  There is no vector "permute/shuffle by index" op in the ISA (checked `valu`/`flow` in
  `problem.py:254-335`), so you cannot turn "16 resident values + index vector" into a cheap
  select. **S2b reduces to S1's flow wall. Likely dead.**

**Functions/locations that would change if any salvage survives Day-1:**
- `_emit_vec_round` (`perf_takehome.py:321-449`): add a `depth == 4` branch mirroring the
  `depth == 3` mux (lines 358-395), guarded by a flow-budget check.
- `build_kernel` setup region (`perf_takehome.py:529-609`): add `vload` of `tree[15..30]`
  into two contiguous vectors + their broadcasts, analogous to the `d3_tree_vec` block
  (lines 581-608). Store engine is free at setup, so precompute cost ~0 cycles.
- No new ISA ops; uses existing `vload`, `vselect`, `v_alu("&")`.

**Data structures:** a `c["d4_*"]` broadcast set (16 entries) and reused `mtmp` groups
(the `NUM_MTMP_GROUPS` machinery, `perf_takehome.py:599-608`).

---

## 4. Day-1 experiment (smallest thing to validate/kill fast)

Two commands. The first **kills the naive hash-LUT in one shot** by confirming the load-cost
arithmetic; the second checks whether the salvage (S1/S2) has any room by measuring flow slack.

```bash
# (A) Reproduce baseline + prove load is saturated in the middle (KILLS the "idle load" premise)
python3 -u -c '
from perf_takehome import KernelBuilder
kb=KernelBuilder(); kb.build_kernel(10,2047,256,16)
I=kb.instrs; N=len(I); print("CYCLES",N)
from collections import Counter; c=Counter()
for b in I:
    for e,s in b.items(): c[e]+=len(s)
print("engine totals",dict(c),"load floor",c["load"]/2)
for st in range(0,N,150):
    seg=I[st:st+150]; ld=sum(len(b.get("load",[])) for b in seg); fl=sum(len(b.get("flow",[])) for b in seg); n=len(seg)
    print(f"[{st}-{st+n}] load {100*ld/(2*n):.0f}%  flow {100*fl/(1*n):.0f}%")
'
# Expected: CYCLES 1230; load floor 1098; middle windows load=100%, flow rarely >40%.

# (B) Correctness harness for any change (must print OK + CYCLES)
python tests/submission_tests.py
```

**Kill criterion (naive LUT):** command (A) already shows load 100% in the middle and load
total 2196 — combined with "no gather instr" (section 2a), any hash-LUT adds >=4096 loads.
**Do not build it.** Confirmed dead at Day-0.

**Go/no-go for salvage (S1/S2):** if command (A) shows flow occupancy in the middle band is
**already >70%**, then S1/S2 (which add flow ops) are dead too — stop this lane entirely. If
flow is <40% *and* you can invent a mux that is <=6 flow ops for 16-way (you cannot with only
binary `vselect`: 16-way needs 15), it is still dead. Realistically this lane ends here.

---

## 5. Risks & likely failure modes (honest)

1. **The whole premise is wrong (CONFIRMED).** Load is not idle in the middle; the slack is in
   the same tails already exploited. The lane's founding assumption failed Day-0 measurement.
2. **No gather instruction (CONFIRMED, section 2a).** Any data-indexed LUT is 8 loads/vector.
   This alone makes every hash-LUT variant a net load-floor *increase* of thousands of cycles.
3. **Hash sub-words aren't separable where it pays (CONFIRMED, section 2b).** `>>` stages
   destroy low-bit locality; separable `<<` stages already cost 1 muladd — nothing to offload.
4. **Salvage collides with the flow floor (CONFIRMED, section 2c/S1).** Extending muxes to
   depth 4 adds 960 flow ops → flow floor 1696. Flow (1 slot/cycle) is the true wall on
   gather-reduction, which is *why* OPTIMIZATION_NOTES.md found re-gather and deeper muxes dead.
5. **No permute/shuffle op.** "16 resident node values + per-lane index → select" has no cheap
   ISA primitive; it degrades to flow muxes (flow-bound) or gather (load-bound).
6. **Even a successful load-floor cut may not move cycles.** The binding floor in the middle is
   the *combined alu+valu* throughput (1174) per OPTIMIZATION_NOTES.md; lowering the load floor
   from 1098 only helps if load, not alu+valu, is the local bottleneck at those cycles. In the
   middle both are ~100% simultaneously, so freeing load alone may yield nothing.

**Overall:** this is the highest-risk lane of the set. It is included for completeness and to
*document why it is dead*, so no future agent re-derives it.

---

## 6. Expected payoff & effort

- **Naive hash-LUT (assigned idea):** payoff **negative** (+~1900 cycles). Confidence it beats
  1230: effectively **zero**. Effort to confirm-dead: **0.5 day** (already done here).
- **Salvage S1 (depth-4 mux):** payoff **negative** (flow floor 1696). Confidence: **zero**.
- **Salvage S2 (structural `vload` LUT):** *best case* trims a handful of gather loads in the
  drain tail only, where load is 40-59% and freeing loads lets a few vstore/gather bundles
  co-pack. Realistic payoff **0 to -15 cycles (i.e. 1230 → ~1215..1230)**, and only if it
  doesn't add flow pressure. Confidence it beats 1230 at all: **low**. Effort: **1-2 days**
  to build the depth-4 `vload`+select and sweep, with high probability of a null result.

**Recommendation:** treat this lane as **closed** for the hash-LUT interpretation. If any
engineer-hours are spent, cap at the Day-1 command (A) to re-confirm the load-saturation
picture, then reallocate effort to the alu+valu combined-throughput lane (floor 1174, 56
cycles of real headroom) or to windup/drain scheduling — both of which have live slack that
this lane does not.

---

## 7. Dependencies / prerequisites

- **No new library.** Pure `perf_takehome.py` edits (rule: never touch `tests/`).
- **Scratch budget:** S2b would need ~4 extra vectors (16 depth-4 broadcasts + temps) ~=
  40 words; scratch is 1536, current usage leaves room (build succeeds today). Not a blocker.
- **Store/setup budget:** ample — store engine uses 32/... of thousands of setup cycles, so any
  precompute is free. (This is the one part of the lane brief that is true; it just has nothing
  worth precomputing.)
- **ISA prerequisite that is MISSING:** a vector gather (`vgather dest, idx_vec`) or a vector
  permute/shuffle. Their absence is what kills the lane. If a future problem revision adds
  either op, **reopen this document** — the hash-LUT and S2 both become live immediately, and
  the 132-cycle load headroom becomes real.

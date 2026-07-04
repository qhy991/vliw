# Direction: Flow-Engine Relief — shrink / re-engine the `vselect` muxes

## 1. Direction name + one-line thesis

**Flow-engine relief via selective arithmetic-select substitution.**

Flow (`vselect`) runs at exactly its single-slot floor — 736 ops / 736 cycles = 100% of its own engine floor — and profiling shows it is a genuine *co-limiter* in the two flow-heavy windows (head `[100-175]`, drain `[1130-1180]`). By re-expressing a *targeted subset* of the depth-3 8-way tournament's `vselect`s as arithmetic selects on the alu/valu engines (which have headroom in exactly those windows), we relieve the flow floor where it binds and let the greedy scheduler pull tail work forward.

This is a **narrow, honest** lane: the direct win is small (~7-15 cycles of provable flow-sole-binding), and the upside above that depends on second-order scheduler packing. It is *not* a slam-dunk toward 1174. It is included because flow is the one engine sitting at 100% of its own floor and has never been attacked, and because the drain picture at 1230 has shifted from the notes' "alu-bound tail" to a **valu+flow-bound tail** — which changes what relief is worth.

---

## 2. Why this could beat 1230 (quantitative, tied to verified floors)

### 2.1 Measured flow accounting (verified this session, at 1230 cycles)

Per-engine total slots in the current 1230-cycle program (measured by counting bundles — `cycles == len(kb.instrs)` exactly for `n_groups==1`):

```
load 2196 (floor 1098)   valu 7055 (floor 1176)   alu 13456 (floor 1121)   flow 736 (floor 736)
```

Note the alu/valu split has shifted vs the OPTIMIZATION_NOTES numbers (14336/7009) because the head/tail rebalance moved combines; **flow=736 is unchanged and is the only engine pinned at exactly 100% of its own floor.**

Flow-op breakdown (verified by counting from `_emit_vec_round`, rounds `r`, depth `= r % 11`, `forest_height=10`, `K_VEC=32`):

| Source | vselects/vec | rounds hit | total flow ops | share |
|---|---|---|---|---|
| depth-1 mux (`_emit_vec_round` d==1) | 1 | r=1,12 | 64 | 8.7% |
| depth-2 mux (d==2) | 3 | r=2,13 | 192 | 26.1% |
| **depth-3 mux (d==3)** | **7** | **r=3,14** | **448** | **60.9%** |
| wrap vselect (d==fh==10) | 1 | r=10 | 32 | 4.3% |
| **total** | | | **736** | |

Depth-3 is 61% of all flow traffic. It is the obvious target.

### 2.2 Where flow actually binds (verified windowed profile)

Windowed engine utilization (fraction of slots used), 25-bundle windows in the tails:

```
HEAD:
[ 50-  75] alu 1.00 valu 0.91 load 1.00 flow 0.96
[ 75- 100] alu 1.00 valu 0.89 load 0.04 flow 0.76
[100- 125] alu 1.00 valu 0.91 load 0.36 flow 1.00   <- flow saturated, load idle, valu slack
[150- 175] alu 1.00 valu 0.97 load 0.84 flow 1.00   <- flow saturated
DRAIN:
[1130-1155] alu 0.35 valu 1.00 load 0.16 flow 0.96  <- valu+flow co-bound, alu+load idle
[1155-1180] alu 0.16 valu 1.00 load 0.48 flow 0.96  <- valu+flow co-bound, alu idle
[1180-1205] alu 0.11 valu 0.76 load 0.36 flow 0.84
```

**Binding-set histogram** (how many bundles have each set of engines *at their slot limit*):

```
('alu','flow','load','valu') 560   <- fully packed, no slack anywhere
('alu','load','valu')        399
('alu','flow','load')         46   (valu has slack)
('alu','flow','valu')         39   (load has slack)
('flow','valu')               35   (alu+load have slack)
('flow','load','valu')        30   (alu has slack)
('alu','flow')                14   (valu+load slack)
('flow',)                      7   <- FLOW IS SOLE LIMITER
('flow','load')                4   (alu+valu slack -> flow is the real limiter)
('flow','store')               1
```

### 2.3 The cycles-on-the-table calculation (honest)

- **Provable direct floor**: bundles where flow is the *sole* limiter (`('flow',)` = 7) plus `('flow','load')` = 4 where the only other pinned engine is the non-swappable load but alu+valu are both free. That's **~7-11 cycles** directly recoverable if we could move flow work off those exact bundles into their idle alu/valu — a hard lower bound on the *pure* flow-relief payoff.
- **Indirect / packing upside**: the interesting set is `('flow','valu')`=35, `('flow','load','valu')`=30, `('alu','flow')`=14 — ~79 bundles where flow co-binds with a *single* flexible engine. In the drain, flow=0.96 while valu=1.00: valu is the immediate limiter, but flow is so close that the moment we relieve valu (a different lane's job) flow becomes the wall. Relieving flow *pre-emptively* removes the second wall so a combined attack can actually cash in. On its own, relieving flow here saves little because valu is still full — this is why confidence is **low** for a standalone win.

**Bottom line: 7-15 cycles are defensible; 15-25 requires the scheduler to repack the tails favorably (noisy, per the notes' §5 packing-noise caveat).** This does *not* independently reach 1174; its role is to remove flow as a co-wall so the valu-tail and alu-tail lanes can go further.

---

## 3. Mechanism: exactly what changes in `perf_takehome.py`

All changes are in `_emit_vec_round` (perf_takehome.py lines 321-449) and a small new helper. The ISA (problem.py) offers only a **2-input** `vselect` on the flow engine (problem.py line 308), so an 8-way select needs ≥7 flow ops in a pure tournament — **7 is already minimal for pure-flow.** The lever is therefore *substitution*, not *reduction*, of individual selects.

### 3.1 Arithmetic-select primitive (new helper)

A `vselect(dest, cond, a, b)` where `cond ∈ {0,1}` per lane is algebraically `b + cond*(a-b)`. On this ISA:

```python
def _arith_select(self, dest, cond01, a, b, tmp):
    # dest = b + cond01*(a-b);  cond01 must be exactly 0/1 per lane
    self.v_alu("-", tmp, a, b)                 # tmp = a - b        (1 valu OR 8 alu)
    self.v_muladd(dest, cond01, tmp, b)        # dest = cond01*tmp + b (1 valu; muladd is valu-only)
```

Cost per replaced select: **2 valu ops** (or the sub can go on alu via `v_alu_scalar`, making it 8 alu + 1 valu). Compare to **1 flow op**. This trades the scarce single-slot flow engine for the flexible engines that are *idle in the tails*. Note `multiply_add` is valu-only (problem.py line 259), so at least 1 valu slot per select is unavoidable; the `-` is the alu/valu knob.

**Correctness caveat on `cond01`:** the existing depth-3 code uses `idx&1`, `idx&2`, `idx&4` directly as the vselect condition — legal because `vselect` tests `!= 0` (problem.py line 311). Arithmetic select needs *exactly* 0/1, so `b1=(idx&2)` and `b2=(idx&4)` must be normalized with a `>>1` / `>>2` (1 extra alu/valu op each). `b0=idx&1` is already 0/1.

### 3.2 Targeted substitution policy (mirror the existing `_combine` tail-gating)

Do **not** convert all depth-3 selects — that adds `~16 flexible ops/vec × 448 = ~1024` ops (≈136 cycles of combined-engine work at the 7.5 ops/cycle throughput), which is globally catastrophic in the both-bound middle (the notes already proved global rebalance dies there). Instead, gate by emission position exactly like `_combine` (perf_takehome.py lines 301-313, 230-233, gen_body reset at 683-684):

```python
# new counters, reset per rotation in gen_body alongside _combine_no
self._vsel_no = 0
self._vsel_total = 448          # depth-3 selects this rotation
self._vsel_head = ...           # convert first N depth-3 selects (windup)
self._vsel_tail = ...           # convert last M depth-3 selects (drain)
```

In the depth-3 branch (perf_takehome.py lines 358-395), wrap each of the 7 `vselect` emissions in a chooser: if this select's global index falls in the head/tail band, emit `_arith_select` (valu/alu); else emit the flow `vselect` as today. Because emission order tracks schedule position (diagonal emission, per notes §4.1), the head/tail bands land in the windup/drain windows where alu/load are idle.

**Refinement — which of the 7 to convert:** the tournament is 3 levels (L1: 4 selects on b0, L2: 2 on b1, L3: 1 on b2; perf_takehome.py lines 371-395). Converting **L2+L3 (3 selects/vec)** is cleaner than L1: L2/L3 already recompute `b1`,`b2` into `addr` (lines 384, 392), so we add only the 0/1 normalization there and leave L1's 4 selects on flow. That cuts depth-3 flow from 7→4 per vec for gated vectors (a 43% flow cut on the converted copies) while adding only ~6 valu ops/vec — a far better ratio than converting L1.

### 3.3 Secondary target: the wrap vselect (32 ops)

> **SUPERSEDED BY REVIEW — see `11-dead-code-idx`.** The wrap vselect is not merely
> convertible to a multiply: the *entire* round-10 idx update (rem `%`, i2p1 muladd, add,
> wrap `<`, wrap vselect) is **dead code**, because round 11 is depth 0 and never reads
> idx. Deleting it (verified correct on 3 seeds, measured −128 valu −32 flow) strictly
> dominates the multiply substitution below. Do not implement this subsection; land
> `11-dead-code-idx` instead and treat this lane as depth-3-only.

The wrap (perf_takehome.py lines 445-449) is `idx = mask ? idx : 0`, i.e. `idx = mask * idx` since the false-branch is 0 and `mask ∈ {0,1}` (it's `idx < n_nodes`, line 446). This is a **pure multiply, no select needed at all**: replace the flow `vselect` with `self.v_alu("*", idx, addr, idx)` (1 valu/alu op, 0 flow). This removes all 32 wrap flow ops unconditionally and correctly, and round 10's wrap lands at ~cycle 700-800 — worth checking if it helps or if those bundles aren't flow-bound (if not, it's free insurance for later combined attacks). ~~This is the single cleanest sub-change and should be done first.~~

### 3.4 Tertiary: depth-2 mux (192 ops)

depth-2 (lines 339-357) is a 4-way select = 3 vselects. The final combining select (line 355, `hi ? inner_hi : inner_lo`) can likewise become arithmetic (`hi ∈ {0,1}` from `4 < idx`, line 348). Lower priority — depth-2 is only 26% of flow and its rounds (2,13) sit nearer the both-bound middle.

---

## 4. Day-1 experiment (smallest thing to validate/kill fast)

**Measurement harness** (cycles == bundle count; deterministic across seeds):

```bash
cd /Users/haiyan-mini/Agent4Kernel/vliw
python3 - <<'EOF'
from perf_takehome import KernelBuilder
kb = KernelBuilder(); kb.build_kernel(10, 2047, 256, 16)
print("CYCLES:", len(kb.instrs))
EOF
```
(Baseline prints `1230`. Note: run this *from* the repo dir — the module uses a package-relative import of `problem`.)

**Correctness** (must pass, unseeded random inputs, tests/ untouched):
```bash
cd /Users/haiyan-mini/Agent4Kernel/vliw && python tests/submission_tests.py   # expect OK + CYCLES
```

**Day-1 sequence (fastest kill/confirm):**

1. ~~**Wrap-as-multiply (Ā§3.3)**~~ **superseded:** the round-10 wrap is dead code entirely (see `11-dead-code-idx`); its deletion is already measured (−32 flow among other things). Rebase this lane on top of that change; the "does removing 32 flow ops move anything" question is answered by that measurement (naive drop-in: floors fell, cycles did not — the tail knobs must be re-tuned).

2. **Instrument before coding the mux change:** dump the binding histogram and per-bundle flow-sole-limiter set (script already validated this session) to see exactly *which cycles* the wrap change and each candidate select removal would land on. If the depth-3 tail selects don't overlap the `('flow',*)`-limited bundles, stop.

3. **L2+L3 tail-only conversion (Ā§3.2 refinement)** with a tiny sweep `_vsel_tail ∈ {0, 32, 96, 224}` (multiples of the 7/vec granularity), `_vsel_head=0` first. Measure cycles for each. Since one full build is fast, sweep head×tail on a coarse grid as the notes did for `_combine_head/_combine_tail`.

**Kill criterion:** if wrap-as-multiply + best tail conversion doesn't reach ≤1228 within the Day-1 grid, the standalone lane is a ≤2-cycle tweak and should be shelved (or handed to a *combined* valu+flow tail attack, see Ā§7).

---

## 5. Risks & likely failure modes (honest)

1. **Valu is the true drain wall, not flow.** Verified: drain `[1130-1180]` has valu=1.00 while flow=0.96. Converting flow→valu there *adds* valu pressure and can make it **worse** — the arithmetic select's `multiply_add` is valu-only. Mitigation: push the `-` onto alu (idle in drain, 0.16-0.35) via `v_alu_scalar`, keeping only the mandatory 1 muladd on valu. But that still adds ≥1 valu/select into a valu-saturated window. **This is the primary reason confidence is low.**
2. **Only ~7-11 cycles are provably flow-sole-bound.** The binding histogram is unambiguous: 560 bundles are quad-bound (perfectly packed) and can't improve. The recoverable set is tiny; everything beyond ~11 cycles is scheduler-packing luck (notes §5 explicitly flags this response surface as noisy, ±3-4 cycles).
3. **Global regression risk.** If the head/tail gating is even slightly too wide, converted selects leak into the both-bound middle `[200-1100]` where every engine is ~100% — adding *any* op there is pure cycle cost. The notes proved global rebalance dies exactly this way. The `_vsel_head/_vsel_tail` bands must be conservative.
4. **7 is minimal for pure-flow depth-3.** No amount of cleverness reduces an 8-way 2-input-select tree below 7 selects. The only reductions are (a) substitution to other engines, or (b) re-gather (already proven dead: d3→1380, notes §3). So flow-op *count* reduction is off the table; only *engine reassignment* remains.
5. **Adds scratch pressure.** `_arith_select` needs a `tmp` vector per concurrent conversion; scratch is tight (SCRATCH_SIZE=1536, all 32 vectors already fit snugly per notes). May need to reuse `mtmp`/`node`/`addr` carefully to avoid `alloc_scratch` overflow (line 244 asserts).

---

## 6. Expected payoff & effort

- **Expected cycles: 1205 (optimistic) — 1228 (likely).** Confidence **low** that it independently beats 1230 by a meaningful margin. The wrap-as-multiply sub is near-certain to be correctness-safe and might contribute 0-2 cycles; the depth-3 tail conversion is where the 5-20 cycle upside lives but is gated by the valu-wall risk (Ā§5.1).
- **Effort: 2-3 days.** Day 1: wrap sub + instrumentation + L2/L3 tail sweep (kill/confirm). Day 2: head-band sweep, alu-vs-valu placement of the `-` op, scratch-reuse cleanup. Day 3: combined head×tail grid + correctness hardening.
- **Best framing:** treat this as a *prerequisite/enabler* for a combined valu+flow tail attack rather than a standalone win. On its own it's a low-confidence 5-15 cycles; as the "remove the second wall" half of a joint drain attack it could unlock a larger shared payoff.

---

## 7. Dependencies / prerequisites

- **No external libraries.** Pure edits to `perf_takehome.py`. `tests/` (incl. `frozen_problem.py`) untouched — HARD RULE.
- **Scratch budget:** need 1-3 extra scratch vectors for `_arith_select` temps unless `node`/`addr`/`mtmp*` can be reused within the depth-3 branch. Audit `alloc_scratch` usage (lines 612-632) before adding vectors; the assert at line 244 will catch overflow.
- **Instrumentation script** (bundle binding-set histogram + per-window utilization + flow-sole-limiter bundle list) — validated working this session; keep it as `_prof.py` run from the repo dir. It is the fast oracle for "does this band overlap a flow-bound cycle."
- **Coupling to the `_combine` tail policy:** the new `_vsel_head/_vsel_tail` bands interact with the existing `_combine_head=10/_combine_tail=100` (lines 232-233) because both compete for valu in the drain. Any sweep of the vselect bands should be re-checked against the combine bands — ideally a small joint 2D-ish sweep, since the notes found the combine tail response surface noisy.
- **Sequencing dependency:** highest value if run *after* (or jointly with) a valu-tail-relief lane, because the drain's binding engine is currently valu, not flow — relieving flow alone into a full valu engine is the documented failure mode (Ā§5.1).
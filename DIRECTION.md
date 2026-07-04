# Direction: Global Multi-Knob Autotuner over the Engine-Assignment Mask

## 1. Direction name + one-line thesis

**Global Multi-Knob Autotuner.** Replace the hand-tuned 2-scalar `(_combine_head, _combine_tail)` heuristic with a real optimizer (coordinate descent seeded, then simulated annealing) over the **full discrete per-combine engine-assignment mask** plus the structural knobs (`step`, `rot`, per-block step-schedule, `NUM_MTMP_GROUPS`), driven by the **exact bundle-count oracle** and parallelized across the 10 cores. Because the scheduler's greedy packing responds *nonlinearly and noisily* to which combines sit on alu vs valu, a search over the fine-grained mask can express placements no scalar head/tail rule can, and reclaim a large fraction of the 56-cycle gap between 1230 and the 1174 throughput floor.

## 2. Why this could beat 1230 (quantitative tie to floors/bottlenecks)

**The knob being optimized is already proven to matter and is correctness-free.** From `OPTIMIZATION_NOTES.md` §1.2: a vector XOR emitted as `v_alu("^", ...)` costs 1 valu slot; emitted as `v_alu_scalar("^", ...)` costs 8 alu slots. The bits are identical (verified in the machine model — `problem.py:263-265` shows `valu` op-word `(op,dest,a1,a2)` loops `alu` over 8 lanes, giving the exact same per-lane result as 8 scalar `alu` ops at `problem.py:219-252`). So **every one of the `3 * K_VEC * rounds = 3*32*16 = 1536 combine instances is an independent free 0/1 choice** (alu-heavy vs valu-heavy). That is a `2^1536` search space — far beyond what the current 2-scalar rule `gi < head or gi >= total - tail` (`perf_takehome.py:310`) can reach. The head/tail rule can only select a *contiguous prefix + suffix* of that mask; it cannot, e.g., valu-ize a specific interior combine that happens to unblock a windup stall.

**Where the cycles are (from notes §3):**
- `middle [200-1000]`: alu ~100% AND valu ~100% — no free slots, the mask should stay alu-heavy here (matches current middle policy).
- `windup [0-100]`: alu 83% / valu 43% — valu has ~57% idle slots.
- `drain [1100-1249]`: alu 14-94% / valu 2-45% — valu massively idle.
- Only **17/1249 bundles are pure dependency stalls**; the rest of the gap is engine-fill imbalance in the tails.

**Cycles theoretically on the table:** combined throughput floor = **1174** (notes §2). Current = 1230. Gap = **56 cycles**. Notes §5 estimates ~19 cycles were "recoverable" *under the head/tail parameterization* and the last few were packing luck. The autotuner's thesis is that the head/tail parameterization itself is the ceiling, not the mask: a finer mask can push materially past the 19-cycle heuristic estimate because it can target *individual* stall-inducing bundles rather than moving contiguous blocks that also perturb the saturated middle (which is exactly why "crude global rebalance" and "depth-selective rebalance" died in notes §3 — they were coarse). A realistic target is 1200-1215 (reclaiming 15-30 of the 56); an optimistic outcome approaching the 1174 floor is possible only if the middle turns out not to be as hard-saturated as the profile suggests.

**Why noise is an argument *for* this, not against:** notes §5 explicitly says neighboring `(head,tail)` configs jump 1230-1240. A noisy, multi-modal, non-convex response surface is precisely the regime where black-box optimizers (SA/CMA-ES) beat human grids — a grid samples a lattice and reports the best lattice point; an annealer follows gradients-of-opportunity between lattice points and escapes local basins.

## 3. Mechanism: exactly what changes in `perf_takehome.py`

The core insight is to **decouple the search from correctness**: the mask only chooses `v_alu` vs `v_alu_scalar` for combines, which the notes and machine model prove is arithmetically identical. So we can search freely and validate cheaply.

### 3.1 Generalize `_combine` to consult an explicit mask (replaces `perf_takehome.py:301-313`)

Today `_combine` uses `self._combine_no` counter + `head`/`tail` scalars. Change it to index an explicit per-instance boolean list:

```python
def _combine(self, dest, a, b):
    gi = self._combine_no
    self._combine_no += 1
    # mask[gi] == 1  -> valu (1 slot);  0 -> alu (8 slots)
    if self._combine_mask is not None:
        use_valu = self._combine_mask[gi]
    else:
        # fallback to legacy head/tail so existing behavior is reproducible
        use_valu = (gi < self._combine_head
                    or gi >= self._combine_total - self._combine_tail)
    if use_valu:
        self.v_alu("^", dest, a, b)
    else:
        self.v_alu_scalar("^", dest, a, b)
```

Add `self._combine_mask = None` in `__init__` (near `perf_takehome.py:230`). The mask has length `_combine_total = 3*K_VEC*rounds` and is set per build attempt by the harness.

**Note on the `val ^= node_src` XOR** (`perf_takehome.py:407-410`): this is a *fourth* per-(vec,round) combine currently keyed on `depth<4`. It is *also* a free alu/valu knob (same identity). Extend the mask to cover it too (a second mask array `_xor_mask` of length `K_VEC*rounds`), for `1536 + 512 = 2048` total free bits. Day-1 can ignore this and add it in phase 2.

### 3.2 Structural knobs (currently hard-coded)

- `step = 4` at `perf_takehome.py:675`. Promote to `self._step`. The 640-combo `(step,rot,key)` grid is exhausted *as a standalone grid* (notes §3), but never *jointly* with a non-trivial mask — the interaction is unexplored.
- **Per-block step-schedule** (new): `gen_body` (`perf_takehome.py:679-716`) uses one global `step` for all blocks via `ppos[j]//step`. Generalize to a per-block start-offset vector `start_offsets[block]` so windup blocks can be spaced differently from drain blocks. This is a small integer-vector knob (length `ceil(K/step)` ~ 8).
- `NUM_MTMP_GROUPS = 3` at `perf_takehome.py:599`. Notes §3 swept it standalone (3 optimal). Include as a joint knob (2-6) since its optimum may shift under a different mask.
- The scheduler is single-key greedy: `key = lambda i: (-hgt[i], -succ[i], i)` at `perf_takehome.py:197`. The 5 `KEYS` (`perf_takehome.py:131-137`) are all defined but only `[0]` is used. **Expose the key index as a knob** — trivially cheap, and the mask changes the op-graph so the best key may differ from the historical winner.

### 3.3 The search harness (new module, imported/invoked from `build_kernel`, or a standalone script)

Put the optimizer in a **separate driver script** (e.g. `autotune.py`) that repeatedly constructs `KernelBuilder`, sets the knobs, and calls a *stripped* build path. Do NOT run the optimizer inside the shipped `build_kernel` (it would blow the build-time budget). Instead: run the autotuner offline, then **hard-code the winning mask + knobs** into `build_kernel` as a literal (a `bytes`/`bitarray` constant keyed on the fixed `(10,16,256)` shape). The shipped kernel just does one build with the frozen winner.

**Oracle (objective function):** the key efficiency win — do NOT run all 32 rotations per candidate. Factor `gen_body(rot)` + `Scheduler().schedule(prefix + rnd)` (`perf_takehome.py:719-723`) into a callable `count_cycles(mask, step, key_idx, rot, ...) -> len(bundles)`. For search, evaluate a **single fixed rotation** (the historical best `rot=29` per notes §3, or the current per-run best) → **~6s per candidate** (measured: full 32-rot build = 189s, so 1 rotation ≈ 6s). Only the *final* champions get the full 32-rotation sweep for validation.

**Encoding + optimizer:**
- **Phase A — coordinate descent from the known-good seed.** Initialize the mask to *exactly* what `head=10,tail=100` produces (so the search starts at 1230, never worse). Then sweep single-bit flips in the tail regions (notes prove middle is saturated, so freeze mask bits for combines whose scheduled bundle index landed in [200,1000] in the seed schedule — this shrinks the effective search space from 2048 bits to the ~400-600 tail bits that can matter). Accept any flip that reduces cycles. This is embarrassingly parallel: 10 cores each test a disjoint batch of single-bit flips against the current incumbent.
- **Phase B — simulated annealing** over the reduced tail-bit vector to escape the coordinate-descent local optimum. Neighbor = flip 1-3 random tail bits (+ occasionally perturb `step`/`key_idx`). Metropolis acceptance with a geometric cooling schedule. Restart from best-so-far on plateau.
- **CMA-ES** is listed in the task but is a poor fit for a pure binary mask (it is continuous). If used, apply it *only* to the low-dimensional continuous-ish knobs (a per-region "valu-probability" schedule that is then thresholded to bits), not the raw mask. Recommend SA over the mask as primary; keep CMA-ES as a fallback for the real-valued step-schedule knob.

**Parallelization across 10 cores** (`multiprocessing.Pool(10)`): each worker imports `perf_takehome`, receives `(mask, knobs)`, returns `cycle_count`. The oracle is pure-Python and CPU-bound with no shared state → near-linear 10x. At 6s/eval that is ~100 evals/min across the pool. A 6-hour run = ~36k single-rotation evals — enough for a serious SA trajectory.

## 4. Day-1 experiment (smallest thing to validate-or-kill fast)

**Goal: prove the mask is finer-grained-useful than head/tail *at all*, in < 30 min of compute.**

Step 1 — build the single-rotation oracle and confirm it reproduces 1230-class numbers:

```bash
python -c "
import time
from perf_takehome import KernelBuilder
kb=KernelBuilder(); kb.build_kernel(10,2047,256,16)
print('baseline full-build CYCLES:', len(kb.instrs))
"
```
(Confirmed: prints `1230`, ~189s.)

Step 2 — implement §3.1 mask + a `count_cycles(mask, rot=29)` single-rotation oracle, then run a **20-minute coordinate-descent** restricted to tail bits, on 10 cores:

```bash
python autotune.py --shape 10 16 256 --seed-from-headtail 10 100 \
    --oracle single-rot --rot 29 --cores 10 \
    --phase coord-descent --budget-min 20 | tee autotune_day1.log
```

**Kill criterion:** if coordinate descent (which *cannot* go above the 1230 seed) finds **zero** single-bit flips that improve the single-rotation count in 20 min, the mask has no headroom the head/tail rule missed → downgrade confidence to low and pivot to the scheduler-replacement direction. **Go criterion:** any improving flip (even 1-2 cycles on the single-rotation oracle) proves the fine-grained mask reaches configurations the scalar rule cannot → greenlight Phase B (SA) overnight.

Step 3 — **validate the Day-1 champion with a full 32-rotation build + correctness**, to distinguish real gain from single-rotation-oracle artifact:

```bash
# after hard-coding the champion mask into build_kernel:
python tests/submission_tests.py   # must print OK and CYCLES < 1230
```

## 5. Risks & likely failure modes (honest)

1. **Single-rotation oracle ≠ 32-rotation reality.** The shipped build takes the *min over 32 rotations* (`perf_takehome.py:719-723`). A mask that wins at `rot=29` may not be the min-over-rotations winner; the packing noise (notes §5) lives exactly here. *Mitigation:* search on single-rotation for speed, but re-rank the top ~50 candidates with the full 32-rotation build before declaring a winner. Budget for this: 50 × 189s ≈ 2.6 hrs.
2. **Overfitting to packing noise.** A 2-3 cycle "win" on one rotation can be scheduler luck, not structural. *Mitigation:* require a champion to beat 1230 on the *full 32-rotation* build AND survive `submission_tests.py`'s 8 correctness runs. Report only full-build-validated numbers. Treat single-rotation gains < 4 cycles as noise.
3. **The middle really is hard-saturated.** If both engines are genuinely 100% in [200,1000], no mask helps there and the ceiling is the tail headroom only (~19 cycles per notes §5's estimate) — the low end of the payoff range. This is the most likely reason the result lands near 1210-1220 rather than near 1174.
4. **Search-space too large even after tail-restriction.** 400-600 free bits is still huge for SA in 6s/eval. *Mitigation:* the coordinate-descent seed drastically prunes; also group bits by (round, block) into ~50 macro-knobs (each a small integer "how many of this group's combines go valu") to cut dimensionality, trading expressiveness for tractability.
5. **Correctness regressions from the *structural* knobs.** The mask is provably safe, but `step`, per-block step-schedule, and `NUM_MTMP_GROUPS` change *scheduling/scratch reuse*, not arithmetic — still safe by construction (they only reorder independent ops and pick mtmp groups), but a bug in the per-block step-schedule refactor (`gen_body`) could misroute a dependency. *Mitigation:* every candidate that changes structural knobs must pass a correctness check, not just a cycle count. Keep structural knobs OFF in Phase A (mask-only, provably safe) and introduce them only in Phase B with correctness gating.
6. **Diminishing returns vs. effort.** If the answer is "1230 → 1224," that is a 6-cycle win for multi-day effort — technically a success over 1230 but below the ambition. The Day-1 kill criterion exists precisely to fail fast before sinking days.

## 6. Expected payoff + confidence + effort

- **Expected cycles:** optimistic **1195**, likely **1210-1226**. (Optimistic assumes the mask reclaims most tail headroom; likely assumes the saturated middle caps gains near the notes' ~19-cycle estimate but the finer mask beats the head/tail heuristic's actual realized value.)
- **Confidence it beats 1230 at all: medium.** The knob is proven-relevant and the head/tail rule is provably a strict subset of the mask, so *some* improvement is plausible; but the saturated middle and packing noise cap the upside, and it is possible the head/tail optimum is already near the mask optimum for the tails.
- **Effort:** Day 1 = oracle + coordinate-descent harness (~1 day). Phase B SA + parallel driver + validation pipeline (~1-2 days). Structural-knob integration + correctness gating (~1 day). Total **3-4 days** to a validated result, with a clean Day-1 kill gate.

## 7. Dependencies / prerequisites

- **Refactor:** extract `gen_body` + `Scheduler().schedule` into a standalone `count_cycles(knobs)` callable so the harness can invoke it without the full `build_kernel` setup each time (or accept the setup cost — it is small vs. the schedule cost). Add `self._combine_mask` / `self._xor_mask` fields and generalize `_combine` (§3.1). Promote `step`, `NUM_MTMP_GROUPS`, `key_idx` to instance knobs.
- **Library:** `multiprocessing` (stdlib) for the 10-core pool. Optionally `cma` (pip) *only* if pursuing CMA-ES for the continuous step-schedule; not required for the primary SA-over-mask path. No heavy deps needed.
- **Compute budget:** ~6s/single-rotation eval × 10 cores. A meaningful run is 4-6 hours (SA trajectory) + ~2.6 hrs final full-build re-ranking of top-50. Fits comfortably in a multi-day effort.
- **Scratch/state:** none beyond existing. The winning mask ships as a hard-coded literal in `build_kernel` keyed on the `(10,16,256)` shape (the shipped kernel must NOT run the optimizer — build-time budget). Provide a shape-guarded fallback to the current `head=10/tail=100` behavior for any other shape so non-target shapes still build correctly.
- **Hard rules:** never touch `tests/` (incl. `frozen_problem.py`); every full-build champion must pass `python tests/submission_tests.py` (8 unseeded correctness runs) and print `CYCLES < 1230`. Only `perf_takehome.py` (and an offline `autotune.py` that is not part of the submission path) may change.
- **Interlock with other lanes:** if a parallel direction changes the op-graph (e.g. reassociates the hash or replaces a mux), the mask must be re-optimized against that new graph. The autotuner is a *meta-lane*: it should run last, or be re-run whenever another lane lands, consuming whatever new knobs those lanes expose (per the task's "any knobs the other directions expose").

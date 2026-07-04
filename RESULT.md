# Result: 10-autotuner — 1230 → 1208 cycles (verified)

## Outcome

**1230 → 1208 cycles** (120.11x → **121.97x** over baseline 147734), verified by
`python tests/submission_tests.py` (`OK`, 8 unseeded correctness runs,
`CYCLES: 1208`). `git diff origin/main -- tests/` empty. Only `perf_takehome.py`
is on the submission path.

Three composed wins, each verified independently:

1. **Per-position emit-offset schedule** (the autotuner's core contribution).
   Generalized `gen_body`'s uniform `p//step` diagonal stagger to an explicit
   length-K per-position offset vector `_pos_offset`, then ran a black-box
   search over it. This is exactly the direction's thesis — a finer knob reaches
   schedules the scalar rule cannot. On the original op-graph: 1230 → 1223.

2. **K5-deferral op reduction** (adopted from lane `02-hash-opcount` per the
   meta-lane mandate in DIRECTION.md §7, re-verified bit-exact here via
   `algebra_check_ported.py`). Defers the hash's trailing `^K5` across round
   boundaries into K5-baked node broadcasts (−224 valu body ops), plus the
   bundled dead-idx-vload removal and next-round-depth-0 skip (drops the round-10
   wrap). valu floor 1170 → 1112, flow 736 → 704, load 2174 → 2111.

3. **Re-optimization on the reduced graph.** K5 shifted the argmin rotation and
   the drain composition, so the pre-K5 offsets/mask were stale. Re-swept
   head/tail (10/100 → 24/100 → 1215), then re-ran the offset search on the K5
   graph → a strongly non-uniform emission order → **1208**.

## Final state is a joint local optimum

All three engine/schedule knobs were driven to convergence on the K5 graph at
1208 (offsets fixed at the champion):
- **combine mask** single-bit descent (rot=28 argmin oracle): **0 improving flips**.
- **xor mask** (512 `val^node` engine choices) single-bit sweep: **0 improving flips**.
- **offset** hill-climb from the champion: nothing below 1208.

The remaining gap (1208 vs the ~1114 K5 balance floor) is the irreducible tail
effect: **99% of bundles have an engine maxed** (measured), and the binding
engine rotates bundle-to-bundle across the windup/drain (alu 1094, load 1066,
flow 704, valu 932 binding-counts at 1208), so no single-engine rebalance or
schedule reshape closes it. Greedy list-scheduling is near-optimal for the
op-graph; the lever that remains is pure op-count reduction.

## Why the mask (the direction's primary bet) was a dead end

Measurement economics were **30-50x cheaper** than DIRECTION.md assumed: a
single-rotation build is ~0.1-0.3s (not 6s), a full 32-rot build ~3.4s (not
189s). The old `autotune_measure.log` showing 50-80s/rotation was `Pool(10)`
over-subscription on a 4-perf-core machine. So exhaustive sweeps were cheap:

1. Single-bit combine-mask sweep from seed(10,100), rot=31: **0 improving flips**.
2. Joint (step, head, tail) grid, 75 full builds: (4,10,100)=1230 optimal.
3. Structural grid (step × key_idx × num_mtmp_groups): (4, key∈{0,2}, 3)=1230.
4. Engine-slot sensitivity is **non-monotonic** (`alu×2 → 1275`, `load×2 →
   1228`, both WORSE) — the classic greedy list-scheduling anomaly, i.e. the
   kernel is resource-bound with a rotating bottleneck, not packing-bound.

The offset schedule is the one lever that helps because it reshapes *when
independent vector work becomes ready*, restructuring windup/drain overlap
without touching any op or any arithmetic.

## Why op-count reduction is now near-exhausted

K5 is the **unique** deferrable hash constant: only the last stage's output
enters the next round via XOR (which commutes with the K5-baked node); stages 0,
2, 4 are muladds and stages 1, 3 feed a multiply, so their constants cannot be
pulled through (XOR is nonlinear w.r.t. `*`). Verified algebraically. The 3
muladd-folded + 3 XOR-combine hash stages are otherwise minimal.

## The change (perf_takehome.py)

- `Scheduler.schedule(key_idx)` + fast incremental scheduler (pre-existing infra).
- `_pos_offset` hook in `gen_body` (defaults to `p//step`); shape-guarded literal
  `_POS_OFFSET_32x16` for the fixed (K_VEC=32, rounds=16) shape.
- Combine mask default built from head/tail=24/100 (shape-guarded).
- K5-deferral: `_emit_vec_round` `defer_k5`/`enter_x` flags, K5-baked node
  broadcasts (`nb0_x`, in-place `nb1/nb2`, `nb3..6`, `d3_*`), parity-swapped
  traverse, dead-idx-vload removal, next-round-depth-0 skip.

All correctness-safe: the mask/offset knobs only choose engine / reorder
independent work; K5-deferral is bit-exact (algebra_check_ported.py: 0
mismatches over 8 shapes incl. the real fh=10/rounds=16). Non-target shapes fall
back to the uniform diagonal + head/tail heuristic.

## Offline search harness (not on the submission path)

- `search.py`, `sweep_under_offset.py`, `descent_under_offset.py` — combine/xor
  sweeps + coordinate descent (rot oracle).
- `grid_struct.py`, `grid_joint.py`, `sweep_ht_k5.py`, `grid_ht_under_offset.py`
  — full-build config / head/tail grids.
- `sched_lab.py`, `sched_keys.py` — scheduler-priority-key experiments (all 1217;
  confirmed scheduler near-optimal).
- `search_offsets*.py`, `anneal_joint.py` — the per-position offset search (the win).
- `descent_mask_k5.py` — mask descent on the K5 graph (confirmed 24/100 optimal).
- `algebra_check_ported.py` — independent bit-exactness proof of K5-deferral.

## Verification

```
python -c "import perf_takehome as P; kb=P.KernelBuilder(); \
  kb.build_kernel(10, 2**11-1, 256, 16); print(len(kb.instrs))"   # -> 1208
python tests/submission_tests.py     # -> OK, CYCLES: 1208
git diff origin/main -- tests/       # -> empty
```

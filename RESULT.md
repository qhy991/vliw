# Result: 10-autotuner — 1230 → 1208 cycles (verified, and still searching)

## Outcome (so far)

**1230 → 1208 cycles** (120.11x → **121.97x**), verified by
`python tests/submission_tests.py` (`OK`, 8 unseeded correctness runs,
`CYCLES: 1208`). `git diff origin/main -- tests/` empty. Only `perf_takehome.py`
on the submission path.

Composed wins:
1. **Per-position emit-offset schedule** — generalizing the uniform `p//step`
   diagonal stagger to an explicit length-K offset vector (the autotuner
   thesis: a finer knob reaches schedules the scalar rule cannot). Reached 1223
   on the original op-graph.
2. **K5-deferral op reduction** (adopted from lane `02-hash-opcount` per the
   meta-lane mandate in DIRECTION.md §7) — defers the hash's trailing `^K5`
   across round boundaries into K5-baked node broadcasts, deleting 224 valu
   body ops (+ bundled dead-idx-vload / round-10-wrap removals). Dropped the
   valu floor 1170 → 1112, re-swept head/tail 10/100 → 24/100 → **1215**.
3. **Offset re-search on the K5 graph** — K5 shifted the argmin rotation (31→0)
   and the drain composition, so the old offset schedule was stale. A fresh
   black-box search found a strongly non-uniform emission order → **1208**.

The K5-graph balance floor is ~1114 (alu≈valu≈1114, load 1056, flow 704), so
1208 still has a ~94-cycle tail-scheduling gap; further offset/mask co-search
is running.

## History / prior milestone

The first-half work established (all measured) that the **mask and config levers
are exhausted on the original op-graph**, then found the offset schedule:

## What the direction predicted vs. what happened

DIRECTION.md bet on the **per-combine engine-assignment mask** as the primary
lever. That bet was **wrong** — the mask is exhausted (see below). But the
direction's fallback structural knob (§3.2, "per-block step-schedule") turned
out to be the real lever, generalized here to a full per-position offset vector.

## The diagnostic chain (why the mask was a dead end, and what actually binds)

Measurement economics were **30-50x cheaper** than DIRECTION.md assumed: a
single-rotation build is ~0.1-0.3s (not 6s), a full 32-rotation build ~3.4s
(not 189s). The old `autotune_measure.log` showing 50-80s/rotation was
`Pool(10)` over-subscription on a 4-perf-core machine. So exhaustive sweeps are
cheap and I ran many.

Key oracle fact: **rot=31 is the argmin rotation** (shipped build = min over 32
rotations). So `count(mask, rot=31)` is a *guaranteed upper bound* on the
shipped number — any mask beating 1230 at rot=31 is a guaranteed shipped win.

1. **Single-bit combine-mask sweep from seed(10,100), rot=31: 0 improving
   flips** (all 1536 bits). The seed mask is a strict local optimum.
2. **Joint (step, head, tail) grid, 75 full builds: (4,10,100)=1230 optimal**,
   nothing beats it. The notes tuned head/tail *for* step=4; their interaction
   is not a new lever.
3. **Structural grid (step × key_idx × num_mtmp_groups), 40 full builds:**
   (step=4, key∈{0,2}, groups=3) = 1230 optimal.
4. **99% of bundles (1201/1217 body) have ≥1 engine maxed** — only 16 are pure
   dependency stalls. The greedy scheduler is **near-optimal for this op-graph**;
   we are resource-bound, not packing-bound.
5. Engine floors (body): valu **1170** (binding), alu 1121, load 1087, flow 736
   — all below 1217. The 47-cycle gap (1217 → 1170) lives in the windup/drain,
   where the *binding engine rotates bundle-to-bundle* (no single global
   bottleneck) and too few vectors are in flight to fill both engines.
6. Engine-slot sensitivity is **non-monotonic** (`alu×2 → 1275`, `load×2 →
   1228`, both WORSE) — classic greedy list-scheduling anomaly. This confirms
   more capacity doesn't help; only reshaping *when work becomes ready* does.

The offset schedule is precisely a "reshape when work becomes ready" lever: it
changes when each vector's rounds are emitted, which restructures the windup/
drain overlap without changing any op or any arithmetic.

## The change (perf_takehome.py)

- Generalized `gen_body`'s diagonal offset `ppos[j] // step` to consult an
  optional per-position vector `self._pos_offset` (defaults to `p // step`, so
  behavior is unchanged when unset).
- Added `_POS_OFFSET_32x16`, the searched winner, applied only for the fixed
  `(K_VEC=32, rounds=16)` shape; other shapes keep the uniform diagonal.
- `_pos_offset = None` field in `__init__`.

```
_POS_OFFSET_32x16 = [0,0,1,0,1,1,1,1, 2,2,2,2,3,3,3,3,
                     4,4,4,4,6,5,5,6, 6,7,6,6,7,7,7,7]
```

Correctness-safe by construction: offsets only reorder independent vector work
(every vector still runs every round with identical ops); the 8 unseeded
correctness runs confirm it.

## Offline search harness (not on submission path)

- `search.py` — combine/xor single-bit sweeps + coordinate descent (rot=31 oracle).
- `grid_struct.py`, `grid_joint.py` — full-build structural / (step,head,tail) grids.
- `sched_lab.py`, `sched_keys.py` — scheduler-priority-key experiments (all 1217).
- `search_offsets.py/2/3` — the per-position offset search that found the win.

## Status / next

- `search_offsets3.py` (aggressive seeded search) was still running at handoff;
  if it beats 1225 on a full build, update `_POS_OFFSET_32x16` and re-run
  `submission_tests.py`.
- The realistic ceiling for this lever is bounded: valu floor is 1170 and the
  drain is dependency-shaped, so the offset schedule can recover tail slack but
  not the ~9 cycles down to the valu floor without an op-count reduction. The
  hash is algebraically irreducible (3 muladd-folded + 3 XOR-combine stages
  confirmed), so op-count reduction has no obvious remaining target.

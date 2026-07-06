# Wave-6 @ 1111 — Orthogonal axes for sub-1000 (2026-07-06)

## Why prior wins did NOT stack
Every landed lever so far was a **shuffle**, not an elimination:
- `D3_GATHER_MASK` / `D4_COLD_MASK`: move ops between **load ↔ flow** (gather↔mux/vload).
- `_combine_mask` / `_xor_mask` / `_const_flow_mask`: move ops between **alu ↔ valu** (1-slot vs 8-slot).

A shuffle redistributes a **conserved** op count. Stacking two shuffles makes them
fight for the same slots / emit-order → measured regressions (1111 base: W2+W3→1116,
unions→1133-1159). Shuffles are single-axis local optima, not composable.

## The orthogonal decomposition
```
realized = max(load, alu, valu, F) + tail        F = (8·valu + alu)/60
```
The four engine floors are **independent**, and `tail` is pure scheduling (op-count
invariant). To reach 1000 EVERY floor must drop below 1000:

| engine | floor@1111 | must cut | lever family (ELIMINATION, not shuffle) |
|--------|-----------:|---------:|------------------------------------------|
| load   | 1083.5     | −84      | const→flow (real flow headroom 743), new vload clusters, scratch reclaim |
| alu    | 1036.7     | −37      | traverse `&`/`<` extract elimination, hash-XOR structural cut |
| F/valu | 1028.9/1027| −29/−27  | algebraic hash fusion (fewer madd/xor/shift TOTAL), like s2+s3(-512)/K5-defer(-224) |
| tail   | 27.5       | keep low | rotation count, pos_offset, emit-order, windup/drain overlap |

**Orthogonality test (MANDATORY before landing):** an axis is valid only if it
lowers ITS engine's op *total* (or tail) **without raising another engine's total**.
Report the full 5-engine floor vector before/after every candidate. If your change
raises another engine to compensate, it is a shuffle — reject it.

## Stackability contract
- Each axis edits a **disjoint code path** and, where possible, is gated by its own
  env/flag so combinations can be A/B tested by env, not by cherry-pick.
- Land on your own branch, but keep the change minimal & localized so the final
  merge onto `explore/wave6-1120` is a clean union of disjoint hunks.
- Real redundancy note: gather-load (2080) is **data-dependent** (256 distinct
  addrs, per-element idx) — the "1824 redundant loads" seen by a naive counter is a
  scratch-reuse ARTIFACT, not real CSE. Same for madd/vbroadcast repeats. Do NOT
  chase CSE on those; cut via vectorization/algebra/scheduling instead.

## Axes
- **O1 load** (`v120-d4cold-wide`, win-in-progress): const→flow full sweep + vload clusters. Fixed d3/d4 masks.
- **O2 valu/F** (`v111-valu-fusion`): algebraic hash fusion — reduce madd/xor/shift op TOTAL. Hardest-value, highest F payoff (8× weight on valu).
- **O3 alu** (`v111-alu-cut`): eliminate traverse extract `&`/`<` and reduce hash-XOR alu expansion TOTAL (not move it to valu).
- **O4 tail** (`v111-tail-pack`): pure scheduling — rotations, pos_offset, emit-order, windup/drain. Op-count invariant, trivially orthogonal.

Gate for all: `CYCLES < 1111` PSPACE=1, `PSPACE=0 <= 1187`, parity 0 + algebra ALL-PASS.

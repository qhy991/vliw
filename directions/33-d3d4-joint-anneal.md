# Direction W6-C: JOINT d3_gather × d4_cold anneal — **WIN 1120→1111**

**Status:** LANDED @ 1111 (2026-07-06). Branch `explore/v120-d3d4-joint` @ c31f27c.
Driver `experiments/anneal_d3d4_joint.py`. New shipped defaults:
- `D3_GATHER_MASK = {0,1,2,3,4,34,35,44,45,50,54}` (11 positions)
- `D4_COLD_MASK   = {7,12,16,22,24,33,37}` (7 positions)

`D3_GATHER_MASK=[]` / `D4_COLD_MASK=[]` still disable each lever.

## Thesis — the two masks must be co-searched
The two levers pull opposite directions on the **load** engine:
- **d3 gather** converts a depth-3 flow-mux → scalar gather: **ADDS** load, but
  packs the schedule tail (drops flow ops out of congested windows).
- **d4 cold** converts a depth-4 gather → vload-mux: **REMOVES** load.

Measured decomposition on the shipped graph (full-32, PSPACE=1):
| config | realized | Δ |
|---|---:|---:|
| neither mask | 1152 | — |
| d3-only (old champ) | 1148 | −4 |
| d4-only (old champ) | 1134 | −18 |
| both (old champ) | 1120 | −32 |
| **both (joint SA)** | **1111** | **−41** |

d3-alone is worth only −4 but **−14 on top of d4** → strong d3↔d4 **synergy**. A
single-axis search (tune d3 alone, or d4 alone) cannot see it; only a joint
64⊗64-bit search does. The old 1120 champ was itself a joint point; this axis
re-annealed **both masks together from scratch** and found a better balance.

## Search method (decisive)
- **Oracle proxy:** the omni rot-27 single-rotation build (~0.33s) is a measured
  **strict upper bound** on full-32 realized — 24/24 champion-neighborhood
  samples had `full ≤ oracle`, diff ∈ [−144, 0]. So `oracle < 1120` *guarantees*
  `full < 1120`. Cheap accept signal; every collected mask batch-confirmed on the
  slow full-32 build (~10s) with the dual PSPACE gate.
- **Two-phase SA** (`anneal_d3d4_joint.py`): Phase-1 pure-oracle SA co-perturbs
  1–2 bits across both masks (sparse-bias to keep masks lean), collecting every
  distinct mask with oracle ≤ 1128; Phase-2 batch full-confirms the best-by-oracle
  top-K and applies the gate.
- **Diverse restarts matter:** the 1111 basin was found only by the hot-start
  seed (T0=3.5), NOT the local-refinement seed (T0=2.5, bottomed ~1119). The
  winning d4 family is `{7,12,16,22,24,33,37}` — completely disjoint from the old
  `{25,26,27,29,31,34}`. Full-space SA with hot restarts is required; a warm local
  search around the 1120 champ under-explores.

## Pareto (realized vs load) — it is a TAIL/PACKING win, not a floor drop
Confirmed landable masks, best realized per load level:
| realized | PSPACE0 | load |
|---:|---:|---:|
| **1111** | 1180 | **1083.5** |
| 1112 | 1182 | 1079.5 |
| 1115 | 1182 | 1075.5 |
| 1117 | 1181 | 1071.5 |
| 1118 | 1182 | 1059.5 |

**The best realized has the HIGHEST load.** Pushing load down (more d4-cold)
*hurts* realized here — the win comes from tail packing via the joint mask, and
the champion keeps load relatively high (1083.5, near the un-masked 1087.5). The
load floor is not the binding limiter for this lever; the greedy scheduler tail
is. Implication for other axes: a pure load-floor mover will not help realized
until the tail-packing headroom on this axis is exhausted.

## Gate (all pass)
`parity_check.py` 0 violations · `algebra_check_ported.py` ALL-PASS (bit-exact) ·
`tests/submission_tests.py` **1111** · `PSPACE=0` **1180** (≤1187 gate).

## Remaining headroom
Many masks confirm in the 1111–1119 band (9 distinct realized values), so the
d3×d4 joint axis has a dense low-realized plateau but 1111 is the current floor
across two diverse-seed full-space runs + one dispatched-workflow run. Further
joint-mask gains are likely <1 cycle (diminishing returns, same signature as the
d3-sparse axis converging around 1120→1111). Below 1111 needs either a genuinely
new lever or a load-floor mover that also improves the tail.

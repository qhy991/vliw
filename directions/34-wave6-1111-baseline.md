# Wave-6 baseline @ 1111 (2026-07-06)

**Branch:** `explore/wave6-1120` (HEAD tracks joint-SA champ from `explore/v120-d3d4-joint`).

## Shipped graph
- `tests/submission_tests.py` **1111** · `PSPACE=0` **1180** (≤1187 gate)
- `D3_GATHER_MASK` default `{0,1,2,3,4,34,35,44,45,50,54}`
- `D4_COLD_MASK` default `{7,12,16,22,24,33,37}`
- Disable either: env `D3_GATHER_MASK=[]` / `D4_COLD_MASK=[]`

## Engine profile (PSPACE=1)
```
load  1083.5  BIND
alu   1036.7
F     1028.9  (=(8·valu+alu)/60)
valu  1027.0
flow   743.0  (huge headroom)
tail    27.5
```

## Path to 1000 (−111 cycles)
1. **Real load-floor cut** on fixed d3+d4 masks: const→flow (51 const), new vload
   clusters, scratch reclaim — NOT more d4-cold (Pareto NO-GO).
2. **Co-bind cut** after load≈F: combine/xor/const_flow SA re-seeded on 1111 graph.

## Active axes (post-1111)
| Axis | Worktree | Focus |
|------|----------|-------|
| A→B | `v120-d4cold-wide` | Pivot: const→flow + vload (d4 SA done) |
| C | `v120-d3d4-joint` | Converged @ 1111; infra only |
| B | `v120-load-shed` | const→flow / vload (partial) |
| D | `v120-cobind-cut` | Re-seed combine SA on 1111 |
| E | `v120-omni-joint` | Full omni SA from 1111 seed |

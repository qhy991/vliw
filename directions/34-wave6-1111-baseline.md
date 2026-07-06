# Wave-6 baseline @ 1111 (2026-07-06)

**Branch:** `explore/wave6-1111` (global best; perf from `explore/v120-d3d4-joint` joint-SA champ `c31f27c`).

## Exploration ledger (all @ 1111, 2026-07-06)

| Axis | Verdict | Doc |
|------|---------|-----|
| O1 load (const→flow, vload, co-bind) | NO-GO | `34-wave6-1111-baseline.md` §Axis B (d4cold-wide) |
| O2 valu/F fusion | NO-GO | `O2-valu-fusion-NOGO.md` |
| O3 alu b0-carry | **LANDED gated** (`B0_CARRY=1`, default OFF) | `36-O3-alu-cut.md`, `37-O1-O3-stack-union.md` |
| O4 tail pos_offset | NO-GO | `O4-tail-pack-NOGO.md` |
| scratch-reclaim | NO-GO (21w free; E2 costs 48w) | `38-scratch-reclaim-1111.md` |

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

## Next steps (post-exploration)

All orthogonal axes at 1111 are closed or gated. Sub-1111 requires a **new d5+
gather representation** (algorithmic, not engine rebalance). Banked lever:
`B0_CARRY=1` stacks after any real load-floor cut (`37-O1-O3-stack-union.md`).

# Direction: Merged floor-movers (#11 + #02 + #03)

Stack order (all on this branch):

1. **#11 dead-idx** — round-10 traverse+wrap + idx vloads deleted; combine 24/100
2. **#02 K5-deferral** — selective 7-round x-space carry; baseline **1215 cycles**
3. **#03 parity-carry** — shallow node-select keyed on raw `rem` vectors (in progress)

## Current task (#03)

Implement parity-carry per `directions/03-round-structure.md` §3 on the 1215 base.

**Phase 1 (landed):** depth-1 `&`-extract removal — `rem_{r-1}` already in `addr`
from the previous traverse; `vselect(node, addr, nb2, nb1)` replaces `idx&1`.

**Phase 2 (blocked on scratch):** depth-2/3 need 2–3 rem history slots; only ~65
scratch words free. Options: overlap rem ring with `node`/`addr` lifetimes, or reduce
`NUM_MTMP_GROUPS`, before landing d2/d3.

## Measurement

```bash
python parity_check.py          # algebra gate for #03
python algebra_check.py         # K5 gate for #02
python tests/submission_tests.py
```

## Goal

Beat **1215** with correct parity-carry on top of the merged #11+#02 kernel.

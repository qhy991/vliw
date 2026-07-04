# RESULT: Merged floor-movers (#11 + #02 + #10 + #03)

**Status:** VERIFIED WIN. `tests/submission_tests.py` → OK.

## Headline

| | cycles | speedup |
|---|---|---|
| #10 autotuner (K5 + offset 1208 base) | 1208 | 121.97x |
| + #03 depth-1 parity-carry | **1208** | **121.97x** |

Net: parity-carry removes 64 valu ops (−1 `&` per depth-1 round × 2 rounds × 32 vec)
with **zero cycle regression** on the 1208 offset schedule — the windup/drain was
already tight enough to absorb the floor drop without re-tuning combine/offset.

## Stack (this branch)

1. **#11** dead-idx elimination (from #10 base)
2. **#02** K5-deferral (−224 valu)
3. **#10** per-position offset `_POS_OFFSET_32x16` + combine mask 24/100 → **1208**
4. **#03 phase-1** depth-1 parity-carry on `rem_{r-1}` in `addr` (K5-aware branches)

## Not yet landed

- Depth-2/3 parity-carry (scratch budget)
- Further offset/mask re-search after d2/d3 op drops

## Verification

```bash
python parity_check.py
python algebra_check_ported.py   # from 10-autotuner
python tests/submission_tests.py  # OK, CYCLES: 1208
```

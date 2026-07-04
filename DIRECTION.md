# Direction: Merged floor-movers

Base: **`10-autotuner` @ 1208** (K5 + offset + combine mask). Do not regress below 1208.

## Stack

| # | Lane | Status |
|---|------|--------|
| 11 | dead-idx | in base |
| 02 | K5-deferral | in base |
| 10 | offset `_POS_OFFSET_32x16` | in base → 1208 |
| 03 | parity-carry | **phase-1 done** (depth-1) |

## #03 phase-1 (landed)

Depth-1: `vselect(node, addr, nb_lo, nb_hi)` keyed on `rem_{r-1}`; K5 flip when `enter_x`.

## Next

- Depth-2/3 parity-carry (scratch ~88 words free on 1208 base)
- Re-run offset search only if d2/d3 op drops move cycles below 1208

## Verify

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py   # must stay OK, CYCLES <= 1208
```

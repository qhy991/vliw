# RESULT: Merged floor-movers (#11 + #02 + #10 + #03)

**Status:** VERIFIED WIN. `tests/submission_tests.py` → OK. **CYCLES: 1208**

## Headline

| Milestone | cycles | Δ from prev |
|---|---|---|
| Baseline | 1230 | — |
| #11 + #02 + #10 (offset + K5) | 1208 | −22 |
| + #03 depth-1 parity-carry | **1208** | 0 |
| + #01 D3 gather port (tested) | 1208 or 1211 | **no win** |

**Global best remains 1208** (121.97x).

## Stack (shipped)

1. **#11** dead-idx elimination
2. **#02** K5-deferral (−224 valu)
3. **#10** `_POS_OFFSET_32x16` + combine mask 24/100
4. **#03 phase-1** depth-1 parity-carry (−64 valu, absorbed by schedule)

## #01 D3 gather port (negative on 1208 graph)

Drain-tail mux→gather ported (`_d3_gather_tail`, `_gather_node`, K5-bake after gather).
On the **K5+offset 1208 graph** (unlike the 1230 graph where #01 got −12):

| `D3_GATHER_TAIL` | `combine_tail` | full 32-rot cycles |
|---|---|---|
| 0 (off, **shipped**) | 100 | **1208** |
| 6 | 90 | 1208 (tie) |
| 8 | 100 | **1211** (regression) |

Conclusion: offset schedule already reshaped drain; D3 gather trades flow for load
but perturbs the tuned combine/offset balance. **Default `_d3_gather_tail=0`.**
Enable via `D3_GATHER_TAIL=8` only for experiments.

## Not yet landed

- #03 depth-2/3 parity-carry / p-space traverse
- Re-search offset/mask after op-count drops

## Verification

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py  # OK, CYCLES: 1208
```

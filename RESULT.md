# RESULT: Merged floor-movers (#11 + #02 + #03 phase-1)

**Status:** VERIFIED WIN (phase-1). `tests/submission_tests.py` → OK.

## Headline

| | cycles | speedup |
|---|---|---|
| #11 + #02 base (combine 24/100) | 1215 | 121.59x |
| + #03 depth-1 parity-carry (combine 28/100) | **1214** | **121.69x** |

Net: **1215 → 1214** (−1 cycle) from depth-1 `&`-extract removal (−64 valu ops)
plus combine re-sweep **24/100 → 28/100** on the new op profile.

## What changed

1. **Inherited from #11+#02** (branch `explore/merged-floor` at fbfa970):
   dead-idx elimination, K5-deferral, combine hooks.
2. **#03 phase-1:** depth-1 node-select keyed on `rem_{r-1}` in `addr` (parity-carry).
   K5-aware branch order when `enter_x` (always true at depth-1 in this shape).
3. **Re-sweep:** `_combine_head=28`, `_combine_tail=100` (was 24/100).

## Not yet landed

- Depth-2/3 parity-carry (−320+ valu ops budget) blocked on scratch (~65 words free).
- K5-graph offset schedule from #02 window (1208 candidate) not ported.

## Verification

```bash
python parity_check.py      # 0/4096 invariant, 0/512 depth-1 node
python algebra_check.py     # ALL-PASS
python tests/submission_tests.py  # OK, CYCLES: 1214
```

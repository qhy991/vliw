# Direction: Merged floor-movers (integration branch)

**Base:** `explore/merged-floor` @ **1208 cycles**. Do not regress.

## Landed

| # | Lane | Notes |
|---|---|---|
| 11 | dead-idx | skip r10 traverse/wrap; no idx vload |
| 02 | K5-deferral | −224 valu; 7 selective defer rounds |
| 10 | offset + combine | `_POS_OFFSET_32x16`, head/tail 24/100 |
| 03 | parity phase-1 | depth-1 `rem` vselect; 0 cycle win |
| 01 | D3 gather port | default off on 1208 graph |

## Next (in order)

1. **#12 p-space** — `directions/12-pspace-traverse.md`. Flag `PSPACE=1` when implemented.
   Prior attempt reverted; do not commit until tests pass.
2. **Re-sweep** combine mask + offset.
3. **#01 D3 gather** grid: `D3_GATHER_TAIL` × `COMBINE_TAIL`.
4. **#13 mem spill** then **#03 phase-2** d2/d3.

## Rules

- Fixed shape only: `forest_height=10, rounds=16, batch_size=256`.
- After every op-count change: re-sweep head/tail (and offset if cycles move).
- alu and valu are co-binding — watch combined floor, not valu alone.
- Commit only when `submission_tests.py` prints OK.

## Verify

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py   # CYCLES <= 1208
```

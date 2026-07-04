# Direction: Merged floor-movers (integration branch)

**Base:** `explore/merged-floor` @ **1185 cycles** (PSPACE=1). Do not regress.
`PSPACE=0` falls back to the idx-space 1208 build.

## Landed

| # | Lane | Notes |
|---|---|---|
| 11 | dead-idx | skip r10 traverse/wrap; no idx vload |
| 02 | K5-deferral | −224 valu; 7 selective defer rounds |
| 10 | offset + combine | `_POS_OFFSET_32x16`, head/tail 24/100 |
| 03 | parity phase-1 | depth-1 `rem` vselect; 0 cycle win |
| 01 | D3 gather port | default off on 1208 graph |
| **12** | **p-space traverse** | store `p` not `idx`; −248 valu; annealed re-sweep → **1185** |

## Next (in order)

1. **#01 D3 gather** grid on the post-p-space graph: `D3_GATHER_TAIL` × combine,
   with its own `experiments/anneal_pspace.py` re-run.
2. **#13 mem spill** then **#03 phase-2** d2/d3.

## Rules

- Fixed shape only: `forest_height=10, rounds=16, batch_size=256`.
- After every op-count change: re-sweep head/tail (and offset if cycles move).
- alu and valu are co-binding — watch combined floor, not valu alone.
- Commit only when `submission_tests.py` prints OK.

## Verify

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py   # CYCLES <= 1185 (PSPACE default 1)
```

# RESULT: Merged floor-movers — global best **1208**

**Branch:** `explore/merged-floor`  
**Status:** VERIFIED. `tests/submission_tests.py` → OK. **CYCLES: 1208** (122.30×)

## Engine profile @ 1208

```
valu:  6668 ops / 6 = 1111.3   ← co-binding with alu
alu:  13344 ops /12 = 1112.0
load:  2133 ops / 2 = 1066.5
flow:   704 ops / 1 =  704.0
store:   32 ops / 2 =   16.0
scratch: 1448 / 1536 (88 free)
combined alu+valu floor ≈ 1111.5  |  realized 1208  |  tail gap ≈ 96 (~8.7%)
```

## Landed stack

| # | Change | cycles | Notes |
|---|---|---|---|
| baseline | — | 1230 | |
| 11+02+10 | dead-idx, K5-deferral, offset+combine | **1208** | −22 |
| 03 ph.1 | depth-1 parity-carry (`rem` vselect) | 1208 | −64 valu, absorbed |
| 01 port | D3 gather tail (`_d3_gather_tail`) | 1208 | default **off**; tail=8 → 1211 |

## #01 D3 gather (tested on 1208 graph)

| `D3_GATHER_TAIL` | `combine_tail` | cycles |
|---|---|---|
| 0 (**shipped**) | 100 | **1208** |
| 6 | 90 | 1208 |
| 8 | 100 | **1211** |

Mechanism valid; graph already retuned. Re-grid with `COMBINE_TAIL` if re-enabled.

## Not landed — execution order

See `directions/INDEX.md`. Summary:

1. **#12 p-space** — store parity `p` not `idx`; −256 valu, 0 scratch. **Failed attempt July 2026**
   (borrow mixing on d2/d3; defer-d0 off-by-one). Spec: `directions/12-pspace-traverse.md`.
2. **Re-sweep** `COMBINE_HEAD/TAIL` + offset after each op drop.
3. **#01 D3 gather** — `D3_GATHER_TAIL` × `COMBINE_TAIL` grid on post-p-space graph.
4. **#13 mem spill** — vstore/vload rem history; unlocks #03 phase-2 (−320 valu).
5. **#03 phase-2** — d2/d3 re-permuted parity tables.

**Ceiling (op-count route):** combined floor ≈ 1035 → realized optimistic **1125–1150**,
conservative **~1170**.

## Verify

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py   # OK, CYCLES: 1208
```

## Env knobs

| Variable | Default | Purpose |
|---|---|---|
| `COMBINE_HEAD` | 24 | valu combines in windup |
| `COMBINE_TAIL` | 100 | valu combines in drain |
| `D3_GATHER_TAIL` | 0 | depth-3 mux→gather instances |
| `PSPACE` | 0 | (future) p-space traverse |

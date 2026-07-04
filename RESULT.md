# RESULT: Merged floor-movers — global best **1185**

**Branch:** `explore/merged-floor`  
**Status:** VERIFIED. `tests/submission_tests.py` → OK. **CYCLES: 1185** (124.67×)

## Engine profile @ 1185 (PSPACE=1, shipped default)

```
valu:  6581 ops / 6 = 1096.8
alu:  12056 ops /12 = 1004.7
load:  2141 ops / 2 = 1070.5
flow:   704 ops / 1 =  704.0
store:   32 ops / 2 =   16.0
scratch: 1520 / 1536 (16 free)
combined alu+valu floor ≈ 1097  |  realized 1185  |  tail gap ≈ 88
```

## #12 p-space traverse — LANDED (1208 → 1185, −23)

Store parity `p` in the idx scratch slot (`idx == 2^d−1+p`). Deep-round traverse
collapses to one muladd `p ← 2p+rem` → **−248 valu ops** (valu floor 1111→1070).
Node lookups use clean bits of `p` (no borrow mixing): d1 vselect on `p`; d2
`p&1`,`1<p`; d3 natural table order `[7..14]`; gather `addr = fvp_p_d + p`.
After the drop, ALU became the sole binding floor → **joint offset+combine
re-sweep** (`experiments/anneal_pspace.py`, rot=27 oracle) repacked 1211 → **1185**.
`PSPACE=0` restores the idx-space 1208 path. Correctness: `parity_check` 0/4096,
`algebra_check_ported` ALL-PASS, `submission_tests` OK.

## Prior engine profile @ 1208 (PSPACE=0)

```
valu:  6668 / 6 = 1111.3   alu: 13344 /12 = 1112.0   (co-binding ≈ 1111.5)
```

## Landed stack

| # | Change | cycles | Notes |
|---|---|---|---|
| baseline | — | 1230 | |
| 11+02+10 | dead-idx, K5-deferral, offset+combine | 1208 | −22 |
| 03 ph.1 | depth-1 parity-carry (`rem` vselect) | 1208 | −64 valu, absorbed |
| 01 port | D3 gather tail (`_d3_gather_tail`) | 1208 | default **off** |
| **12** | **p-space traverse + re-sweep** | **1185** | **−248 valu; −23 cycles** |

## #01 D3 gather (tested on 1208 graph)

| `D3_GATHER_TAIL` | `combine_tail` | cycles |
|---|---|---|
| 0 (**shipped**) | 100 | **1208** |
| 6 | 90 | 1208 |
| 8 | 100 | **1211** |

Mechanism valid; graph already retuned. Re-grid with `COMBINE_TAIL` if re-enabled.

## Not landed — execution order

See `directions/INDEX.md`. Summary (#12 now landed → 1185):

1. **#01 D3 gather** — `D3_GATHER_TAIL` × `COMBINE_TAIL` grid on the post-p-space
   graph (PSPACE=1 D3_GATHER_TAIL=6 → 1203 with the current mask; needs its own
   mask/offset re-sweep to beat 1185).
2. **#13 mem spill** — vstore/vload rem history; unlocks #03 phase-2 (−320 valu).
3. **#03 phase-2** — d2/d3 re-permuted parity tables.
4. After every op-count change: re-run `experiments/anneal_pspace.py` (offset +
   combine mask joint re-search).

**Ceiling (op-count route):** combined floor ≈ 1035 → realized optimistic **1125–1150**,
conservative **~1170**.

## Verify

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py   # OK, CYCLES: 1185 (PSPACE default 1)
PSPACE=0 python tests/submission_tests.py   # OK, CYCLES: 1208 (idx-space fallback)
```

## Env knobs

| Variable | Default | Purpose |
|---|---|---|
| `PSPACE` | **1** | p-space traverse (store `p` not `idx`); 0 → idx-space 1208 |
| `COMBINE_HEAD` | 24 | valu combines in windup (idx-space heuristic) |
| `COMBINE_TAIL` | 100 | valu combines in drain (idx-space heuristic) |
| `D3_GATHER_TAIL` | 0 | depth-3 mux→gather instances |

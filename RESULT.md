# RESULT: Merged floor-movers — global best **1179**

**Branch:** `explore/merged-floor`  
**Status:** VERIFIED. `tests/submission_tests.py` → OK. **CYCLES: 1179** (125.30×)

## Engine profile @ 1179 (PSPACE=1, shipped default)

```
valu:  6595 ops / 6 = 1099.2
alu:  11936 ops /12 =  994.7
load:  2141 ops / 2 = 1070.5
flow:   704 ops / 1 =  704.0
store:   32 ops / 2 =   16.0
scratch: 1520 / 1536 (16 free)
combined valu binding ≈ 1099  |  realized 1179  |  tail gap ≈ 80
```

**Binding flipped after #12:** valu is sole binding; alu has ~105 cycles slack.
Co-bind rebalance (#14): 347→300 valu combines (middle segment → alu) → **1184→1179**.

## #12 p-space traverse — LANDED (1208 → 1184, −24)

Store parity `p` in the idx scratch slot (`idx == 2^d−1+p`). Deep-round traverse
collapses to one muladd `p ← 2p+rem` → **−248 valu ops**. Joint offset+combine
re-sweep (`experiments/anneal_pspace.py`) repacked 1211 → **1184**.
`PSPACE=0` restores idx-space 1208.

## #14 co-bind rebalance — LANDED (1184 → 1179, −5)

Post-p-space, the shipped champ mask (347 valu combines) was tuned when alu was
binding. Moving 47 middle combines back to alu (300 on valu) lowers the co-bind
floor without touching correctness. See `experiments/anneal_cobind.py`,
`champ_cobind.json`.

## #10 idx-space re-sweep — LANDED (PSPACE=0: 1208 → 1199, −9)

Cherry-picked W4 (`explore/10-autotuner`) alternating coordinate-descent wins onto
the merged-floor idx-space graph (includes #03 phase-1; not bit-identical to the
10-autotuner K5 graph, so 1198→1199 not 1198). Changes: head/tail **32/130**,
offset idx25/31 tweaks, interior mask gi=1271→valu / gi=1461→alu.

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
| 12 | p-space traverse + re-sweep | 1184 | −248 valu; −24 cycles |
| **14** | **co-bind rebalance (300 valu combines)** | **1179** | **−5 cycles** |
| 10b | idx-space head/tail+mask re-sweep | 1199 | PSPACE=0 fallback only |

## Falsified on p-space graph

| Direction | Result | Verdict |
|---|---|---|
| #01 D3 gather | d3>0 → 1201+ | KILL on p-space |
| #03 idx-space low-bit | 1197 on 1208 graph | not portable to PSPACE=1 |
| #13 mem spill | NO-GO | load floor blocks |

## Remaining levers (ranked)

1. **anneal_cobind.py** — joint mask+offset SA with valu→alu bias (may beat 1179).
2. **d2/d3 valu→alu migration** — push mux extracts to alu slack (Tier B).
3. **scratch liveness** — partial phase-2 if words free up.

**Ceiling (op-count route, revised @ 1179):** co-bind floor ≈ 1079 → realized
optimistic **1125–1145**; **1100** needs new structural wins + tail-gap shrink.

## Verify

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py   # OK, CYCLES: 1179 (PSPACE default 1)
PSPACE=0 python tests/submission_tests.py   # OK, CYCLES: 1199
```

## Env knobs

| Variable | Default | Purpose |
|---|---|---|
| `PSPACE` | **1** | p-space traverse; 0 → idx-space 1208 |
| `COMBINE_HEAD` | 24 | valu combines windup (idx-space heuristic) |
| `COMBINE_TAIL` | 100 | valu combines drain (idx-space heuristic) |
| `D3_GATHER_TAIL` | 0 | depth-3 mux→gather instances |

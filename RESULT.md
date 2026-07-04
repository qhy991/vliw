# RESULT: Merged floor-movers — global best **1174**

**Branch:** `explore/merged-floor`  
**Status:** VERIFIED. `tests/submission_tests.py` → OK. **CYCLES: 1174** (125.84×)

## Engine profile @ 1174 (PSPACE=1, shipped default)

```
valu:  6593 ops / 6 = 1098.8
alu:  11960 ops /12 =  996.7
load:  2141 ops / 2 = 1070.5
flow:   704 ops / 1 =  704.0
store:   32 ops / 2 =   16.0
combined valu binding ≈ 1099  |  realized 1174  |  tail gap ≈ 75
```

**Binding flipped after #12:** valu is sole binding; alu has ~102 cycles slack.
Co-bind rebalance (#14): 347→300 valu combines (middle segment → alu) → **1184→1179**.

## #15 d2/d3 extract valu→alu migration — LANDED (1179 → 1174, −5)

Post-#12/#14 valu is the sole binding floor (~1099) with ~105 alu slack. The 320
d2/d3 traverse *extract* ops (idx&1, 1<p, idx&2, idx&4) all defaulted to valu.
Blanket migration over-shoots (alu → 1208), because the extracts sit in the
saturated middle band, not the idle tails. A **joint (combine, extract, offset)
simulated anneal** (`experiments/anneal_extract.py`) found the 57 individually-idle
extract instances to shed to alu; the win is mostly tighter tail packing (gap
80→75) with a co-tuned combine mask (300→354 valu) and offset vector. New
`v_alu_ex` hook + `_extract_mask` (default None ⇒ all-valu ⇒ identical 1179), and
`_EXTRACT_ALU_PSPACE_32x16` shipped default. Extracts are arithmetically identical
on either engine, so correctness is untouched. See `champ_extract.json`.

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
| 14 | co-bind rebalance (300 valu combines) | 1179 | −5 cycles |
| **15** | **d2/d3 extract valu→alu (joint anneal)** | **1174** | **−5 cycles; tail-pack + 57 extracts→alu** |
| 10b | idx-space head/tail+mask re-sweep | 1199 | PSPACE=0 fallback only |

## Falsified on p-space graph

| Direction | Result | Verdict |
|---|---|---|
| #01 D3 gather | d3>0 → 1201+ | KILL on p-space |
| #03 idx-space low-bit | 1197 on 1208 graph | not portable to PSPACE=1 |
| #13 mem spill | NO-GO | load floor blocks |
| co-bind anneal (mask+offset) | full-32 = 1180 | no win beyond #14/#15 |
| D3-gather anneal | stuck 1184 | no win |

## Remaining levers (ranked)

1. **structural valu-op deletion** — floor barely moved (1099→1099); #15 was a
   packing/rebalance win, so the ~75-cycle tail gap and the 1099 floor are still
   the two prizes. #03 phase-2 (d2/d3 re-permuted parity tables, −320 valu) needs
   scratch first.
2. **scratch liveness** — partial phase-2 if words free up.
3. Re-run `experiments/anneal_extract.py` after any op-count change (joint
   combine+extract+offset SA).

**Ceiling (op-count route, revised @ 1174):** co-bind floor ≈ 1079 → realized
optimistic **1125–1145**; **1100** needs new structural wins + tail-gap shrink.

## Verify

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py   # OK, CYCLES: 1174 (PSPACE default 1)
PSPACE=0 python tests/submission_tests.py   # OK, CYCLES: 1199
```

## Env knobs

| Variable | Default | Purpose |
|---|---|---|
| `PSPACE` | **1** | p-space traverse; 0 → idx-space 1208 |
| `COMBINE_HEAD` | 24 | valu combines windup (idx-space heuristic) |
| `COMBINE_TAIL` | 100 | valu combines drain (idx-space heuristic) |
| `D3_GATHER_TAIL` | 0 | depth-3 mux→gather instances |

# RESULT: Merged floor-movers — global best **1157**

**Branch:** `explore/15-s2s3-fusion`  
**Status:** VERIFIED. `tests/submission_tests.py` → OK. **CYCLES: 1157** (127.69×)

## #15 s2+s3 muladd fusion — LANDED (1174 → 1157, −17)

Fuse hash stages 2 and 3 into `2 muladd + 1 combine`. Both stage-3 operands are
affine in the stage-1 output `a`: `t1 = u+K3 = a*33 + (K2+K3)` and
`t2 = u<<9 = a*16896 + (K2<<9)` where `u = a*33+K2`, so each is one muladd from
`a` directly. This deletes 1 valu-locked op per (vec,round) = **−512 valu**
(6593 → 6081; alu unchanged at 11960). Verified bit-exact vs `myhash` on 500k
random inputs + `parity_check`/`algebra_check_ported`. Consts `K2/K3/sh9` retire;
`K2K3=0xE9F8CC1D / m16896=0x4200 / K2S9=0xACCF6200` are born (net scratch 0).

The floor math flipped the binding engine: valu 6081/6 = **1013.5** now sits
below **load 2141/2 = 1070.5**, which becomes the hard floor. A joint
(combine, extract, offset) re-anneal (`experiments/anneal_extract.py`, warm-start
from the #14/#15 champs) repacks to realize the drop — combines 300→538 valu,
extracts 57→301 on alu, new offset vector — landing **1157** (load 1070.5 + tail
gap ≈ 86). `champ_extract.json` updated. PSPACE=0 fallback also improved
1199 → 1190 (fusion helps the idx-space graph too).

## Engine profile @ 1157 (PSPACE=1, shipped default)

```
valu:  6081 ops / 6 = 1013.5
alu:  11960 ops /12 =  996.7
load:  2141 ops / 2 = 1070.5   <- now binding
flow:   704 ops / 1 =  704.0
store:   32 ops / 2 =   16.0
combined load binding ≈ 1071  |  realized 1157  |  tail gap ≈ 86
```

**Binding flipped again after #15:** valu (1013.5) dropped below load (1070.5);
load is now the sole binding floor. Further valu deletion is absorbed — the next
prize is the load floor and the ~86-cycle tail gap.

## Prior engine profile @ 1174 (PSPACE=1)

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
| 15a | d2/d3 extract valu→alu (joint anneal) | 1174 | −5 cycles; tail-pack + 57 extracts→alu |
| **15** | **s2+s3 muladd fusion + re-anneal** | **1157** | **−17 cycles; −512 valu → load-bound; 538 valu comb / 301 alu ex** |
| 10b | idx-space head/tail+mask re-sweep | 1190 | PSPACE=0 fallback only |

## Falsified on p-space graph

| Direction | Result | Verdict |
|---|---|---|
| #01 D3 gather | d3>0 → 1201+ | KILL on p-space |
| #03 idx-space low-bit | 1197 on 1208 graph | not portable to PSPACE=1 |
| #13 mem spill | NO-GO | load floor blocks |
| co-bind anneal (mask+offset) | full-32 = 1180 | no win beyond #14/#15 |
| D3-gather anneal | stuck 1184 | no win |

## Remaining levers (ranked)

1. **load floor (1070.5) is now binding** — after #15's −512 valu, valu (1013.5)
   dropped below load, so further valu-op deletion is absorbed. The two prizes
   are now the **load floor** (2141 loads/rotation = 8 scalar gathers/deep-round)
   and the **~86-cycle tail gap**. Reducing gathers (vectorized depth-≥2 loads,
   or fewer deep rounds) is the new highest-value structural lever.
2. **tail-gap shrink** — windup/drain packing; the re-anneal took gap 75→86 as it
   traded valu for tighter load packing, so there may be offset headroom left.
3. Re-run `experiments/anneal_extract.py` after any op-count change (joint
   combine+extract+offset SA).

**Ceiling (revised @ 1157):** load floor 1070.5 is the hard wall for the op-count
route; realized **1157** already sits ~86 above it. Beating ~1130 needs the load
floor itself to drop (fewer gathers) — valu/alu rebalance alone cannot.

## Verify

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py   # OK, CYCLES: 1157 (PSPACE default 1)
PSPACE=0 python tests/submission_tests.py   # OK, CYCLES: 1190
```

## Env knobs

| Variable | Default | Purpose |
|---|---|---|
| `PSPACE` | **1** | p-space traverse; 0 → idx-space 1208 |
| `COMBINE_HEAD` | 24 | valu combines windup (idx-space heuristic) |
| `COMBINE_TAIL` | 100 | valu combines drain (idx-space heuristic) |
| `D3_GATHER_TAIL` | 0 | depth-3 mux→gather instances |

# Direction W6-W0 (E2 mirror): depth-3 sparse gather mask — **WIN 1134→1132**

**Status:** LANDED @ 1132 (2026-07-05). Branch `explore/w6-d3-sparse`.
Env `D3_GATHER_MASK` (JSON 0/1 over 64 d3 emit-order instances); shipped default
`{42,50,55}`; `D3_GATHER_MASK=[]` disables → 1134.

## Thesis (and why it is the *mirror* of E2, not a copy)
E2's D4_COLD win removed depth-4 **scalar gathers** from the binding **load**
engine (load 1065→1043, cut the floor). Depth-3 is structurally opposite: d3
rounds already use an **8-way flow-mux** by default (7 flow vselects + 3 valu),
so d3 carries **no load** to remove. The only d3↔gather lever is the reverse —
convert a flow-mux instance **into** a scalar gather (`D3_GATHER_MASK`), which
*adds* 8 loads to the binding engine.

Globally this is the wrong direction: every single-position conversion raises the
load floor 1043 → **1047.5** (uniform, additive). Uniform `D3_GATHER_TAIL` confirms
it (1153…1268; LESSONS L5). So the win is **not** a floor drop — it is a
schedule-hole: a specific instance whose gather drops into an idle-load drain slot
while removing 7 flow ops from a congested local window, tightening the greedy
packing more than the higher floor costs.

## Measured (full 64-position single sweep)
`experiments/probe_d3_mask_cli.py` + sweep. load floor pinned 1047.5 everywhere.

| d3i | realized | Δ vs 1134 | note |
|---|---:|---:|---|
| **42** | **1133** | **−1** | **WIN** — round-14 drain region |
| 44 | 1134 | 0 | neutral |
| 50 | 1134 | 0 | neutral |
| 55, 57 | 1136 | +2 | least-bad tail |
| (most) | 1140–1195 | +6…+61 | regress |
| 10 | 1310 | +176 | worst (windup-adjacent) |

**Combo search** over {42,44,50,41,43,55,57} × sizes {1,2,3}: the triple
**`{42,50,55}` → 1132** (−2) beats the single. `(42,55)`/`(44,55)` reach 1133 but
at a higher load floor; the {42,50,55} triple reaches 1132 at floor 1055.5 — the
three drain-region holes pack jointly tighter than any pair. Shipped default is the
triple. Larger stacks past the tight winner set do not improve (gathers are
additive on the binding engine beyond the available holes).

## Composition with E2
Verified with the shipped `D4_COLD_MASK={25,26,27,29,31,34}` active: the d3 triple
and the d4 sparse mask compose (different rounds/engines) → 1132, PSPACE=0 1181.
Both defaults ship.

## Mechanism detail
- d3 rounds = {3, 14}; 64 d3 instances (2 rounds × K=32), emit-order interleaved by
  the 8-wide diagonal stagger. Positions 42/50/55 are all in the round-14 (drain) half.
- Gather path needs the `fvp_p_3` broadcast (was gated behind `D3_GATHER_TAIL>0`);
  the mask branch now also allocates it. With the default mask always active this
  +1 setup const is live (funds the drain-region gathers).

## Gate (all pass)
`parity_check.py` 0 violations · `algebra_check_ported.py` ALL-PASS ·
`tests/submission_tests.py` **1132** · `PSPACE=0` **1181** (was 1187, improved).

## Remaining headroom
The load floor is now 1055.5 with realized 1132 (gap 76.5). Adding more d3 gathers
only raises the floor. This win does not unlock #27 (load 1055.5 > alu 1036.7, gap
widened). The next load-floor *drop* still requires a scratch-free d4 cut (#26
gated) — d3 gather is a packing/tail lever, not a floor lever.

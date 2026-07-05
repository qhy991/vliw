# Round 4 — Tier-B #26 d4-gather-cut (REAL implementation) — NO-GO

**Date:** 2026-07-05
**Lever:** WAVE-4 Tier-B — partial d4 gather→mux table + node/addr pooling.
**Result:** best achievable **1251** (exhaustive), **+99 over 1152**. NO-GO.
**Global best unchanged: 1152 (PSPACE=1) / 1189 (PSPACE=0).**

This is the FIRST real bit-exact implementation of #26 (the prior NO-GO was
analytical). It confirms and hardens that NO-GO with measured data.

## What landed (kept)

**B1 recycler** (commit ebcbf00): cherry-picked the three #25 free-list commits
onto merged-floor. **48 → 78 free**, cycle-neutral (1152/1189 held, parity 0,
algebra ALL-PASS). This is a clean, safe enabling step and STAYS.

## What was built (behind knobs, default off — 1152 unaffected)

A complete, **bit-exact** depth-4 mux (`_d4_mux_node`, env `D4_MUX`=k):
- 16-way tournament over `nb15..nb30` (tree[15..30]), two 8-way subtrees + b3
  combine. p-space: `idx==15+p`, `node=tree[15+p]`. Depth 4 never enter_x → no
  K5 bake. **Verified: `submission_tests.py` + `algebra_check_ported` ALL-PASS
  at D4_MUX=64.**
- Engine split (`D4_VALU_LEAF`): 8 leaf selects via valu muladd
  (`nb[2t]+b0·d_t`, deltas precomputed) off the 1-slot flow engine; 7 upper
  selects on flow.
- Node/addr pooling (`NODE_POOL_G`=G): pool per-vector node/addr into G shared
  slots to fund the table's scratch.

## Why it fails: pooling penalty > gather prize (measured)

The mux drops the **load floor 1064.5 → 810.5** (prize real, confirmed). But the
128w broadcast table (16 leaves × 8 lanes, irreducible) + delta/temp vectors
cannot be funded from 78 free without node/addr pooling, and pooling serializes
the hash pipeline (node/addr are hash temps too):

```
node/addr pooling penalty ALONE (D4_MUX=0), measured:
  G=32 (none) 1152 | G=28 1199 (+47) | G=24 1221 (+69) | G=20 1253 (+101) | G=16 1315 (+163)

d4 prize ALONE (D4_FREE probe, pure load-floor drop, this graph):
  k=14 1151 | k=24 1120 | k=32 1108 (−44) | k=64 1097 (−55)
```

The table needs G≤24 to fit (G≤20 with the 64w deltas). At G=24 the pooling
already costs +69c; the best k saves only ~−44c. **The scratch-funding cost
structurally exceeds the prize at every operating point.**

**Exhaustive search** (LEAF∈{0,1} × k∈{4,8,16,22,32,48,64} × G∈{16..24}, 70
configs): **best = 1251** (LEAF=1 k=32 G=20). Every point regresses.

## Why the #26 PROBE's "+10c pooling on d4-cut graph" was optimistic

The `probe_node_addr_pool.py` D4_FREE number (+10c) modeled the cut by **deleting
the d4 loads only**. The real mux *adds* 8 valu muladds + 7 flow selects per
instance that compete for exactly the node/addr registers being pooled, so the
real WAR serialization is far worse (+69c at the same G). The prize denominator
was also over-counted: real crossover saves ~44c, not 63c, on this graph.

## Verdict

#26 d4-gather-cut is **NO-GO by real measurement**, not just scratch-gate
analysis. The prize (load floor 810) is genuine but unreachable: 128w table is
irreducible, and the only funding path (node/addr pool) costs more than the cut
saves because node/addr sit on the hot hash path. Sub-1100 via d4-mux is closed.

**Resurrection:** a table representation cheaper than 16 per-lane broadcasts
(none known), OR a scratch source that is NOT the node/addr hot-path (none
found — recycler is exhausted at 78, all other pools are live).

## State

Global best **1152**. B1 recycler landed (78 free, banked for any future
scratch need). #26/#27 closed. The scratch-free plateau (round 3) and the
scratch-gated prize (round 4) are both now exhausted with hard data. 1152 is the
frontier for the known lever set.

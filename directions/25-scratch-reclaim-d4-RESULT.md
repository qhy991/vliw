# Direction #25: Scratch reclaim — PARTIAL LAND (80 free, cycle-neutral) + #26 gate revised

**Branch:** `explore/25-scratch-reclaim-d4` (from `merged-floor` @ **1156**; note
merged-floor has since advanced to **1152** via #28 const→flow — the recycler
touches `alloc_scratch` only, orthogonal to #28's engine rebalance). **Stack
verified:** cherry-picking the 4 commits onto #28 HEAD (f7a4f14) gives **1152
cycles, 79 free** (up from 49), parity/algebra/PSPACE=0 (1189) all clean.
**Status:** clean reclaim **LANDED** — `scratch_ptr 1486 → 1456`, **free 49 → 80`
(80 on the 1156 base, 79 stacked on #28's +1 zero-seed word), cycles unchanged.
The literal `scratch_ptr ≤ 1408` (128-free) gate is **NOT reachable
cycle-neutrally on any graph**; see the pooling probe.

**Reconciliation with round-1 scratch audit ("only 13 words genuinely dead"):**
that audit counted only *trailing* dead words (droppable off the top of the bump
allocator). The free-list recycler reclaims *interior* dead setup scratch by
**reusing** low-address setup-only blocks for high-address body vecs — setup is
a separate scheduled stream that completes before the body, so this is safe. Net
clean reclaim is **30 words, not 13**.

---

## 1. What landed (four commits, each gated parity+algebra+submission+PSPACE=0)

| reclaim | words | mechanism |
|---|---|---|
| orphan `mtmp` vec | 8 | allocated at setup then immediately re-aliased to `mtmp_0`; pure dead scratch |
| `tree_lo` + `d3_tree_vec` vloads | 16 | vload staging read only by `nb*`/`d3_*` broadcasts; dead once body stream starts |
| `fvp_p8` scalar | 1 | `d3_tree_vec` vload base; dead in body |
| single-group loop-control (`vctr/vstride/grp_base/grp_base_v/cond`) | 5 | `n_groups==1` never touches them in the body |
| **total** | **30** | **49 → 80 free (pspace); 117 free in PSPACE=0** |

Mechanism: a **free-list recycler** in `alloc_scratch` (+ `free_scratch`). Setup
emits its own scheduled instruction stream that fully completes before the loop
body, so scratch written only during setup can be handed back and reused by the
per-vector body vecs — dropping the high-water mark with **zero op changes**.

## 2. Why 128 free is unreachable cycle-neutrally

Clean setup-scratch is now exhausted at 80 free. The only remaining pool large
enough to close the 80→128 gap (48 words) is the **per-vector `node`/`addr`
transients** (32 vecs × 16w = 512w). They have no cross-round liveness in
p-space (every depth writes both before reading; only `idx`/`val` carry state),
so they *can* be pooled across vectors like the `mtmp_{g}` temps — but WAR
serialization costs cycles. Measured (`experiments/probe_node_addr_pool.py`):

```
current graph (load-bound 1156):   80→128 free = +33 cyc (1189); ONE share = +14
D4_FREE graph (alu-bound  1093):   80→128 free = +10 cyc (1103)
mtmp 3→1 (also reaches 128):       +19 cyc (1175) on current graph
```

Every path to 128 regresses cycles → fails the literal #25 kill criterion.

## 3. The revision: #26 does not need 128-free as a *pre*-gate

The pooling penalty is a WAR hazard on the path feeding the **d4 gather loads**
— the exact loads #26 deletes. On the post-#26 alu-bound graph the same 48-word
reclaim costs only **+10 cyc**, and the #26 D4_FREE ceiling is **1093** (−63 vs
1156). So the scratch #26 needs is *cheapest to mint inside #26's own anneal*,
not before it:

- 80 clean free words (landed here) fund 10 of #26's 16 `nb15..nb30` broadcasts.
- the remaining 6 (48w) come from node/addr pooling, annealed jointly with the
  d4 mux — its +10 cyc is absorbed well under the 1093 band.

**Recommendation:** cherry-pick the four clean reclaims to `merged-floor` (zero
risk, 80 free unlocked), then open #26 with a **joint (d4_mux, node/addr-pool,
combine, extract, offset)** anneal instead of treating 128-free as a hard gate.
The `probe_node_addr_pool.py` D4_FREE numbers are the #26 seed.

## 4. Kill-criteria disposition

- "Best reclaim path < 80 words net without mtmp regression" → **reclaimed 30
  words (49→80) with zero mtmp use and zero cycle cost.** Clean lever fully spent.
- "Any reclaim regresses cycles / breaks PSPACE=0" → none did; the pooling lever
  that *would* regress is deliberately **not shipped** (kept as a probe).

# Direction #38 — Scratch-reclaim @ 1111 (2026-07-06)

**Branch:** `explore/v111-alu-cut` (from `explore/wave6-1120` @ 1111).  
**Probe:** `experiments/probe_scratch_reclaim_1111.py`  
**Stack test:** `experiments/probe_o1o3_stack.py` + `directions/37-O1-O3-stack-union.md`

## Goal

Fund a real gather-load cut (depth 5–10 scalar gathers = 96% of load) by reclaiming
≥65 clean scratch words beyond the landed #25 recycler. Enable `B0_CARRY=1` stack
only after load binds below alu.

## Measured scratch budget @ 1111

| build | cycles | free | notes |
|-------|-------:|-----:|-------|
| shipped (E2 cold on) | **1111** | **21** | scratch_ptr=1515 |
| `D4_COLD_MASK=[]` | 1143 (+32) | **69** | cold table costs **48w** |
| `D3_GATHER_MASK=[]` | 1135 | 30 | d3 gather path adds resident scratch |

#25 recycler (orphan mtmp, tree_lo/d3_tree_vec, loop-control scalars) is **already
landed** on this graph. The 1111 graph is *tighter* than the 1156 graph that had
80 free: E2 cold-table residency (`d4_lo/hi/stash/bc0/bc1`) consumes the headroom.

## Attempted reclaims (this session)

### 1. mtmp-group bc borrow (eliminate d4_bc0/bc1/d4_stash)

Replace dedicated `d4_bc0`, `d4_bc1`, `d4_stash` with rotated `mtmp_{g}` slots during
`_d4_cold_mux_node`. Saves 16–24w but **regresses cycles**:

| variant | cycles | free | Δ |
|---------|-------:|-----:|---|
| all three eliminated | 1116 | 45 | +5c |
| bc0/bc1 only | 1124 | 37 | +13c |

**Verdict:** NOT cycle-neutral. Diagonal stagger on 1111 makes cross-group mtmp
borrowing serialize WAR hazards far worse than on the 1156 graph (+14c for G=2
there vs +2944c here for node pool).

### 2. node/addr pool (`NODE_POOL_G`)

| G | cycles | free |
|---|-------:|-----:|
| 0 | 1111 | 21 |
| 2 | **4055** | 501 |
| 4 | 2487 | 469 |
| 8 | 1659 | 405 |

**Verdict:** NO-GO on 1111. Frees words but destroys schedule (not the +10..+33c
penalty seen on post-#26 D4_FREE @ 1156).

## O1+O3 stack (completed)

`GATHER_FREE=1` + `B0_CARRY=1` → **997c** with perfect additivity (−54 + −60 = −114).
`B0_CARRY` is **ready to stack** once a real O1 load cut lands. See `37-O1-O3-stack-union.md`.

## Why sub-1111 is still blocked

```
load 1083.5 BIND
  └─ scalar gather 2080 ops = 1040 cyc (96%)
       ├─ d3: muxed (mask fixed)
       ├─ d4: 7/64 cold-vload (E2, −32c vs no-cold but costs 48w)
       └─ d5–d10: 192 instances, need 256w..8192w tables vs 21w free
```

Naive #26 d4 tournament (128w `nb15..nb30`) shortfall: **107w**.  
Depth-5 alone needs **256w** (LESSONS L4: 2× d4 select cost for −8 load).

## Resurrection conditions

Re-open scratch-reclaim only if ONE of:

1. **New gather representation** for d5+ that avoids resident broadcast tables
   (e.g. on-demand scalar gather batching, mem-spill rings, or depth-specific
   algebraic fold) — not mtmp/bc shuffles.
2. **Per-vector footprint cut** without node/addr pooling (currently unknown on 1111).
3. **Accept +5..+13c** scratch-for-schedule trade *and* prove a partial d5 cut still
   nets below 1111 (not attempted — cold mux savings are only −32c at +48w cost).

## Integration order (when a real O1 lands)

1. Land load-floor cut on `explore/wave6-1120` (verify `load < alu`).
2. Enable `B0_CARRY=1` — expect −12..−60c depending on load-cut depth (stack probe).
3. Re-run `anneal_pos_offset.py` with multi-rot oracle on new graph (O4 resurrection).
4. Re-price O2 valu fusion when `max(load,alu) < valu`.

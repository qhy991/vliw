# LESSONS — do-not-repeat registry @ 1134 (2026-07-05)

**Global best:** `explore/merged-floor` @ **1134** cycles (130.28×), PSPACE=1 (PSPACE=0 1187).

This file records **verified kills** so future sessions (human, Claude, KerSor)
do not re-burn worktrees. Every entry has a reproducible probe or committed
NO-GO doc. **Re-open a killed direction only when its stated resurrection
condition is met.**

---

## 1. Binding engine rules (read before any op-count change)

After **#15 s2+s3 fusion** + **#28 const→flow**, the binding floor on the 1152
graph is:

```
load  2129 ops  floor 1064.5  ← BINDING
alu  12440 ops  floor 1036.7
valu  6017 ops  floor 1002.8  (~62 slots slack)
flow    716 ops  floor  716.0
```

**Rule A — floor hierarchy:** realized ≥ max(load, alu, valu, flow, store, F).
Deleting ops on a **sub-floor engine is absorbed** (payoff 0) until that engine
becomes the wall.

**Rule B — re-price every historical verdict:** docs written @ 1179/1208 assumed
valu binding. After #15, **load binds first**; after D4_FREE probe, **alu binds
second** (see §4).

**Rule C — mandatory re-anneal:** after any structural op-count change, re-seed
`omni_anneal.py` (never `--resume` stale champs). Sizes re-probe from emit order.

**Rule D — scratch budget:** measured `scratch_ptr=1488/1536`, **48 words free**
(#28 adds a zero-seed word). No clean ≥79-word reclaim exists — see §3 (V8/V9),
so the **#25 gate stays blocked** and #26 d4-table remains gated.

**Rule E — engine-of-op matters, not just op-count (NEW @ #28):** `const` runs on
**load** (binding); `add_imm` runs on **flow** (idle). Moving setup consts off the
binding engine is a real lever independent of op-count. See §2 A1.

---

## 2. Scheduling / anneal — DO NOT retry

| ID | What | Measured result | Why dead |
|---|---|---|---|
| S1 | `anneal_cobind.py` beyond #14 mask | best FULL32 **1180** @ 1179 graph | no win beyond landed 300-combine rebalance |
| S2 | D3-gather anneal on p-space | stuck **1184** | no packing win |
| S3 | `omni_anneal` combine+extract+offset @ 1156 | 20k iters, best **1156** | seed champ is strong local optimum |
| S4 | Scheduler `key_idx` sweep (5 keys × 32 rots) | key0 **1156** optimal | drain/windup gap not key artifact |
| S5 | CP-SAT / modulo-pipeline / depth-interleave | ≤3 cycles | greedy within 1 of optimal per graph |
| S6 | Per-position offset alone (post-#10) | captured @ 1208 | windup/drain prize taken |
| S7 | `#24` store-broadcast setup pipe | setup is **load-bound** (29 loads), not valu | moving bcasts to store+vload regresses |
| S8 | `#24` setup/body barrier merge | **1192** | greedy mispacks; 5 idle setup slots anyway |
| S9 | `#24` tail-gap repack without floor drop | windup ~48c + drain ~35c load-idle intrinsic | d0–d3 have no gathers to fill load engine |

**Resurrection for S3/S9:** only after a **load floor-mover lands** (load used drops
materially below 2140), then re-run omni-anneal + #24 levers.

---

## 3. Valu / flow op-count — DO NOT retry @ 1156

| ID | Direction | Kill evidence | Resurrection condition |
|---|---|---|---|
| V1 | `#22` traverse phase-2 / extract purge | zero-cost stub: all d2/d3 extracts removed → **1151** (−5); impossible lower bound **1132** still > load floor | load floor < ~1010 (valu rebinds) |
| V2 | `#23` mem-bake universal K5-defer | K1 windup load idle **102<150**; K2 whole-run idle **172<254**; K3 −288 valu absorbed (load binds) | never @ load-bound graph; bake adds +127 load |
| V3 | Blanket d2/d3 extract → alu | **1273** regression | selective mask only (landed @ 1174 as #15a) |
| V4 | `#19a` 2-round hash fuse | algebra kill: hash bijection, full 32-bit liveness | none (structural) |
| V5 | `#03` phase-2 rem-ring | needs **+256–768** scratch; 49 free | after ≥200 scratch reclaimed |
| V6 | `#13` mem spill | load floor blocks | same as V5 |
| V7 | More valu deletion while load=1070 | any −N valu with N<67 floor-slots | load floor drops first |
| V8 | `#27` alu→valu repack @ 1156/1152 | alu(1036.7) **sub-floor** vs load(1070→1064.5 after #28); perfect repack x≈41 → alu=valu≈1009 but binding stays **load**, realized unchanged; omni-anneal combine+extract+offset 4k iters found 0 improving moves. **Re-priced @1152 (#28): still NO-GO** (load 1064.5 still >alu 1036.7, ~28c gap) | load floor drops **below alu 1036.7** via a **scratch-free** cut (#26 d4-table now NO-GO, gate unreachable; #28-class only, ~28c more needed) — then repack pulls alu 1036.7→**F 975.5** (~61c), see #27 NO-GO §2 |
| V9 | `#25` node/addr working-set pooling | G=16 → **1319** (+163) to free 256w; genuinely live across the 32-vector cross-vector pipeline | never (structural pipeline depth) |
| V10 | `#25` mtmp-group reduction for scratch | G=2 frees 73w for **+14c** (1170), G=1 frees 97w for **+19c** (1175); neither reaches the 128w d4 gate cleanly | never (regresses; use d4 table only if a free ≥79w reclaim appears) |

Probe: `experiments/killtest_23.py` (V2), `experiments/probe_27_repack.py` (V8),
round-1 scratch-audit (`experiments/.kersor-vliw/round-2.md`, V9/V10), `#22`/`#27`
NO-GO repro blocks.

**#25 gate verdict:** the literal 128-word gate is unreachable cycle-neutrally
(pooling regresses — V9/V10). **BUT a free-list recycler DID land 30 clean words
cycle-neutrally** on `explore/25-scratch-reclaim-d4` (49→**80 free**, 1156
unchanged, 4 gated commits; **stack-verified on #28 HEAD → 1152, 79 free**): the
round-1 "only 13 dead" audit undercounted — it counted only *trailing*
droppable words, but setup scratch (`tree_lo`/`d3_tree_vec` vloads, orphan
`mtmp`, `fvp_p8`, single-group loop-control) is *reusable* by body vecs because
setup is a separate scheduled stream. Recycler is **ready to cherry-pick**
(commits b0804af 01bdf52 f6549e3 619601d → merged-floor gives 79 free at 1152).
Still short of 128 → d4 table (#26) stays blocked; pursue no-scratch load-floor
drops (A1). See `25-scratch-reclaim-d4-RESULT.md`,
`experiments/probe_node_addr_pool.py` (refines V9: G=29/48w = +33 current / +10
on D4_FREE graph, not "never").

---

## 2b. LANDED load-floor movers (engine rebalance, no scratch)

| ID | Direction | Result | Notes |
|---|---|---|---|
| **A1** | `#28` const→flow (`add_imm` on flow, not `const` on load) | **1156→1152** | first 12 setup consts → flow; N>12 serializes (1-slot flow + zero-seed RAW chain); env `CONST_FLOW_N`, default 12 |
| **A1b** | `#30` per-instance const→flow **mask** (SA-repacked *which* consts route to flow) | **1152→1151** | KerSor variant-r1 beam solver found it; 11 consts (not first-12) via `_const_flow_mask`; realizes the A1 headroom; PSPACE=0 1189→1187; env `CONST_FLOW_MASK` |
| **E2s** | sparse `D4_COLD_MASK` over d4 emit order | **1151→1134** | cold vload mux is too expensive as prefix-k, but a six-instance sparse mask `{25,26,27,29,31,34}` lands in a schedule window; env `D4_COLD_MASK=[]` disables |

**A1 headroom:** the 47 const-loads still on load are **NOT** in less-saturated
cycles — probe `experiments/probe_const_placement.py` shows **46/47 land in
load=2/2 bundles** (16 setup pairs, 31 windup vaddr+vload). But the 31 windup
ones are the per-vector `vaddr` (§2b A2 NO-GO) and the 16 setup ones are
zero-seed-chained (#28 N>12 kill). Re-anneal (Rule C) may still repack the −4.

### 2b NO-GO — engine rebalance that regressed

| ID | Direction | Measured | Why dead |
|---|---|---|---|
| **A2** | `#29` per-vector `vaddr`→flow (`add_imm(va, IVP, j·V)` on idle windup flow) | sweep N=2→1159, 4→1168, 12→1161, 31→1170; **all N>0 regress**, N=0=1152 | each `vaddr` is a **direct RAW producer of its own vload** — moving it to the 1-slot flow engine puts an add_imm on the vload's critical path and serializes the windup. Unlike #28's setup consts (no load consumes them), these ARE on the load critical path. Flow being idle in the band is irrelevant. Probe: `experiments/probe_const_placement.py`. **Resurrection:** never for vaddr (structural: producer-of-load); only revisit if a future edit makes the vaddr non-critical. |

---

## 4. Load mux / gather — DO NOT retry (wrong shape)

| ID | Direction | Kill evidence | What was wrong |
|---|---|---|---|
| L1 | `#16` / `#20` d4 mux via **flow** vselect tournament | k sweep all regress; k=19 → **1215** | 15 flow selects/instance hits 1-slot flow wall |
| L2 | `#20` engine-split selects **without scratch** | need **128w** for nb15..nb30, have **49w** | scratch unreachable |
| L3 | `#20` scratch reclaim via mtmp 3→1 + scalar addr-add | **~1493** realized | reclaim dumps on **alu** (binding after D4_FREE) |
| L4 | `#21` d5 partial mux | min-over-k floor **1060** = post-#20 binding; d5 contribution **0** | d5 is 2.07× select cost of d4 for same −8 load |
| L5 | `#01` D3 gather tail on p-space | **1203+** with current mask | port needs own anneal |
| L6 | `#16` doc "r4-only saves scratch" | r4/r15 share same tree[15..30] table | flat 128w tax regardless of k mask |

**Silver lining (NOT dead):** `D4_FREE` probe (delete all 64 d4 gathers for free):
realized **1088**, load floor **814**, binding flips to **alu 1036.7**. Prize ≈
**68 cycles** if gather replacement avoids L2/L3 traps.

Probe: W0 `#20` branch `RESULT.md` §D4_FREE; `experiments/kill_test_d5.py`.

**#26 probe revalidated on HEAD (2026-07-05, `explore/26-d4-gather-cut` ac7b2a6):**
`D4_FREE=k` env flag (`experiments/probe_d4_free.py`) frees first k of 64 d4 instances.
- k=64: realized **1093** (load 814, alu 1036.7 binds) — prize **63c**, matches §4.
- **Crossover: load ducks under alu wall at k≈12–14**; realized bottoms **~1096 at k≈32**
  then flat (alu-bound). **Do NOT convert all 64** — the alu wall caps realized.
- Select budget to alu wall: **flow +332 ops (22 inst), valu +203, alu ZERO** (at wall).
  Flow-only feasible window **k∈[14,22]**, realized target **~1100–1110**. Wide bottom
  8 leaf-selects → valu-muladd (delta precompute); top levels → flow. **Never per-lane alu (L3).**
- **STILL GATED on #25** (scratch 49<128 free). Probe-only; default build unchanged.
  Doc: `directions/26-d4-gather-cut-PROBE.md`.

**#26 → NO-GO (2026-07-05, `explore/26-d4-gather-cut` f8dce88):** gate #25 proven
**unreachable**. d4 table = **128w irreducible** (16 per-lane broadcasts). Clean
reclaim ceiling **≈14w vs 79 needed**, verified 4 ways: (1) only 14w fully-dead setup;
(2) all 31 vaddr live; (3) `v0_addr`/`v0_node` lifetimes **overlap** (same bundles) →
alias reclaim 0; (4) overlay ceiling 49+72(d3)=**121<128** and d3/d4 adjacent-live.
`mtmp` 3→2 regresses (+14c). Doc: `directions/26-d4-gather-cut-NOGO.md`.
**Resurrection:** a per-vector footprint cut freeing ≥65 clean words w/o alu ops (none known).
**Correction (#25, `explore/25-scratch-reclaim-d4`):** claim (1) is superseded —
a free-list recycler that *reuses* interior dead setup scratch for body vecs
reclaims **30 clean words** (not 14): 49→**80 free**, cycle-neutral, stack-
verified on #28 (1152, 79 free). Still <128 (48w short, only node/addr pooling
left, which regresses), so **the NO-GO verdict is unchanged** — 30w < 65w
resurrection bar. But the recycler is worth cherry-picking (79 free ≫ 49).

**#26 → NO-GO by REAL implementation (2026-07-05, round-4, merged-floor):**
recycler LANDED (ebcbf00, 78 free) + a full **bit-exact** d4 mux built and
measured (stash: "wip: #26 d4-mux real impl"). 16-way tournament over nb15..nb30,
valu-muladd leaves + flow upper selects, node/addr pooling to fund the table.
`submission_tests` + `algebra_check` ALL-PASS at D4_MUX=64 → **the mux is
correct**. But exhaustive (LEAF×k×G, 70 configs) **best = 1251 (+99)**. Root
cause, measured on this graph:
- d4 mux drops load floor **1064.5→810.5** (prize real, ~−44c at k=32 per D4_FREE).
- 128w table (irreducible) + temps need node/addr pooling to fit (78 free).
- **pooling penalty (measured, D4_MUX=0): G=28 +47c, G=24 +69c, G=20 +101c** —
  node/addr are hash temps, so pooling serializes the hot path.
- table needs G≤24 to fit → penalty (+69c) **exceeds** prize (−44c) at every point.
The `probe_node_addr_pool.py` "+10c on d4-cut graph" was optimistic: it deleted
loads only; the real mux adds 8 valu + 7 flow ops/instance competing for the
pooled registers. **Resurrection:** a table cheaper than 16 per-lane broadcasts,
OR scratch from a non-hot-path source (neither known). Doc: `round-4.md`.

**E2 D4_COLD prefix-k → NO-GO, sparse mask → WIN (2026-07-05):** env
`D4_COLD=k` — vload tree[15..30] once (16w) + b0 layer-wise vbroadcast into
bc0/bc1 (40w total scratch, **no pooling**, parity ALL-PASS). Prefix-k is dead:
k=1 **1171** (+20), k=14 **1230** (+79), k=64 **1921**. Root cause is
runtime b0 vbroadcast+flow tax. But `D4_COLD_MASK` over emit order found a
schedule-local window; shipped default `{25,26,27,29,31,34}` gives **1134** with
load **1043**, valu **1025**, flow **805**, PSPACE=0 unchanged **1187**. Seven/eight
wide masks regress; local swaps found no better than 1135. Doc:
`directions/30-d4-cold-vload.md`; probe: `experiments/probe_e2_d4_coldmask.py`.

---

## 5. KerSor / external tooling

| ID | Lesson |
|---|---|
| K1 | `/kersor:optimize` targets CUDA/GPU kernels — **misfires** on Python VLIW scheduler. Use local `anneal_*.py` / `omni_anneal.py` instead. |
| K2 | `#15a` extract migration (1179→1174) was **tail packing**, not floor drop — still valid, already in stack. |

---

## 6. What remains open (Wave-3, ranked)

1. **#25 scratch-reclaim** — LANDED at **78 free** (recycler cherry-picked, ebcbf00). Clean ceiling exhausted; reaching 128 needs node/addr pooling which regresses (see #26 real NO-GO).
2. **#26 d4-gather-cut** — **NO-GO by real implementation** (round-4: best 1251, +99). Prize real (load floor 810) but pooling penalty (+69c@G=24) exceeds gather-cut prize (−44c). Full bit-exact mux in stash. Doc: `round-4.md`.
2b. **E2 D4_COLD sparse mask** — LANDED **1134**. Prefix-k is still NO-GO; do not retry prefix. Further work should re-anneal combine/extract/offset on the 1134 graph and explore sparse-mask neighborhoods only if coupled with a scheduler objective.
3. **#27 alu-repack-post-load** — precondition is now closer but not met: sparse D4 load floor **1043** is still above alu **1036.7**. Revisit only after another ~7 load-floor cycles.

**#26 is NO-GO — not gated, measured.** E2 sparse moved the load floor, but the
128w resident table path remains dead.

Sub-1000 path: sparse D4 is only the first real load-floor move. Need another
~7 cycles load reduction to unlock #27 alu repack, then re-anneal tail packing.

---

## 7. Verification gate (every commit)

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py            # must OK, CYCLES <= 1134 to land
PSPACE=0 python tests/submission_tests.py   # must not regress 1187
```

---

## 8. NO-GO artifact index

| Branch | Commit | Doc / script |
|---|---|---|
| `explore/20-d4mux-engine-split` | ceac584 | `RESULT.md` §#20 |
| `explore/21-d5-partial-mux` | b9875ad | `directions/21-d5-partial-mux-NOGO.md`, `experiments/kill_test_d5.py` |
| `explore/22-traverse-phase2-valu` | 64f3339 | `directions/22-traverse-phase2-valu-NOGO.md` |
| `explore/23-mem-bake-k5-barrier` | c281b49 | `directions/23-mem-bake-k5-barrier-NOGO.md`, `experiments/killtest_23.py` |
| `explore/24-tailgap-setup-pipe` | 0d3cc56 | `directions/FINDING-24.md`, `analyze_gap.py` |
| `explore/19a-2round-fuse` | 1f748dc | `directions/19a-2round-fuse-NOGO.md` |
| `explore/27-alu-repack-post-load` | (this) | `directions/27-alu-repack-post-load-NOGO.md`, `experiments/probe_27_repack.py` |
| `explore/26-d4-gather-cut` | f8dce88 | `directions/26-d4-gather-cut-NOGO.md`, `26-d4-gather-cut-PROBE.md`, `experiments/probe_d4_free.py` |

Cherry-pick NO-GO docs to `merged-floor` when convenient; **LESSONS.md** is the
single entry point.

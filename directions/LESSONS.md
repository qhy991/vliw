# LESSONS — do-not-repeat registry @ 1152 (2026-07-05)

**Global best:** `explore/merged-floor` @ **1152** cycles (128.24×), PSPACE=1.

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

**A1 headroom:** 11 setup consts still on load but in less-saturated cycles;
moving more regressed in the sweep. Re-anneal (Rule C) may repack the −4 further.

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

---

## 5. KerSor / external tooling

| ID | Lesson |
|---|---|
| K1 | `/kersor:optimize` targets CUDA/GPU kernels — **misfires** on Python VLIW scheduler. Use local `anneal_*.py` / `omni_anneal.py` instead. |
| K2 | `#15a` extract migration (1179→1174) was **tail packing**, not floor drop — still valid, already in stack. |

---

## 6. What remains open (Wave-3, ranked)

1. **#25 scratch-reclaim** — free ≥80 clean words without alu regression (enables d4 table). **Clean ceiling proven ≈14w (§4 #26 NO-GO); needs a per-vector footprint cut, none known.**
2. **#26 d4-gather-cut** — **NO-GO** (gate #25 unreachable). Prize real (63c) but parked until a ≥65w clean reclaim appears. Doc: `26-d4-gather-cut-NOGO.md`.
3. **#27 alu-repack-post-load** — *precondition-parked* (V8): on 1156 alu is sub-floor, repack absorbed (NO-GO). **Validated & banked** on D4_FREE: pulls alu 1036.7 → **F 975.5**. Runs only **after #26** as the mandatory re-tune pass.

**Do not start #26 before #25 kill-test passes** (scratch_ptr ≤ 1408).

Sub-1000 path: load floor 814 (D4_FREE) + alu repack + tail gap after floor drop
≈ 1088 − 70 tail → ~1018; need additional load cuts (d5+) or alu structural wins
for <1000.

---

## 7. Verification gate (every commit)

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py            # must OK, CYCLES <= 1156 to land
PSPACE=0 python tests/submission_tests.py   # must not regress 1190
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

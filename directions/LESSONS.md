# LESSONS — do-not-repeat registry @ 1156 (2026-07-05)

**Global best:** `explore/merged-floor` @ **1156** cycles (127.80×), PSPACE=1.

This file records **verified kills** so future sessions (human, Claude, KerSor)
do not re-burn worktrees. Every entry has a reproducible probe or committed
NO-GO doc. **Re-open a killed direction only when its stated resurrection
condition is met.**

---

## 1. Binding engine rules (read before any op-count change)

After **#15 s2+s3 fusion**, the sole binding floor on the 1156 graph is:

```
load  2140 ops  floor 1070.0  ← BINDING
alu  12440 ops  floor 1036.7
valu  6017 ops  floor 1002.8  (~67 slots slack)
flow    704 ops  floor  704.0
```

**Rule A — floor hierarchy:** realized ≥ max(load, alu, valu, flow, store, F).
Deleting ops on a **sub-floor engine is absorbed** (payoff 0) until that engine
becomes the wall.

**Rule B — re-price every historical verdict:** docs written @ 1179/1208 assumed
valu binding. After #15, **load binds first**; after D4_FREE probe, **alu binds
second** (see §4).

**Rule C — mandatory re-anneal:** after any structural op-count change, re-seed
`omni_anneal.py` (never `--resume` stale champs). Sizes re-probe from emit order.

**Rule D — scratch budget:** measured `scratch_ptr=1487/1536`, **49 words free**.
Docs citing "16 free" or "+128 from four/nn_v/zero" are **stale** (#18 already
spent that reclaim).

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

Probe: `experiments/killtest_23.py` (V2), `#22` NO-GO doc repro block.

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

---

## 5. KerSor / external tooling

| ID | Lesson |
|---|---|
| K1 | `/kersor:optimize` targets CUDA/GPU kernels — **misfires** on Python VLIW scheduler. Use local `anneal_*.py` / `omni_anneal.py` instead. |
| K2 | `#15a` extract migration (1179→1174) was **tail packing**, not floor drop — still valid, already in stack. |

---

## 6. What remains open (Wave-3, ranked)

1. **#25 scratch-reclaim** — free ≥80 clean words without alu regression (enables d4 table).
2. **#26 d4-gather-cut** — replace 512 d4 scalar gathers using d4 table **after** scratch solved; target D4_FREE band ~1088.
3. **#27 alu-repack-post-load** — once load drops, alu becomes wall; joint anneal alu↔valu combine/xor/addr-add.

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

Cherry-pick NO-GO docs to `merged-floor` when convenient; **LESSONS.md** is the
single entry point.

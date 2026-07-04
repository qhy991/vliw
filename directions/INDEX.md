# VLIW Kernel Optimization — Direction Index (post-1208)

**Global best:** `explore/merged-floor` @ **1208 cycles** (121.97×), verified `tests/submission_tests.py`.

Fixed shape: `forest_height=10`, `rounds=16`, `batch_size=256`. Score = `len(kb.instrs)`.

---

## Core conclusion (July 2026)

**Scheduling is exhausted.** CP-SAT on the drain tail proved the greedy scheduler is within
**≤1 cycle** of optimal for the fixed op graph; **99% of bundles have at least one engine
saturated**. Per-position offset search (#10) captured the windup/drain repacking prize
(1230 → 1208). Remaining scheduling knobs (#01 CP-SAT, #04 modulo-pipeline, #09
depth-interleave) cannot move the binding floor meaningfully — at best **≤3 cycles**.

**The only lever left is deleting ops** — and gains must be judged on the **combined
alu+valu floor**, not valu alone:

| Engine | ops @ 1208 | floor |
|---|---|---|
| valu | 6668 | 1111.3 |
| alu | 13344 | 1112.0 |
| load | 2133 | 1066.5 |
| flow | 704 | 704.0 |
| store | 32 | 16.0 |

alu and valu are **co-binding** (~1111.5 combined). Deleting valu ops only pays off if
combine-mask rebalancing moves enough ALU combine work back to valu (each combine: alu −8,
valu +1). **Every structural op drop must be followed by a combine-head/tail + offset
re-sweep.**

**Multi-core is dead:** `N_CORES = 1` in `problem.py` (comment: this build uses single core).

---

## What's landed (merged-floor stack)

| # | Direction | Δ cycles | Notes |
|---|---|---|---|
| 11 | dead-idx elimination | part of −22 | skip round-10 traverse/wrap; drop idx vload |
| 02 | K5-deferral (7 rounds) | part of −22 | −224 valu; selective defer across gather boundary |
| 10 | per-position offset + combine mask | **1208** | `_POS_OFFSET_32x16`, head/tail 24/100 |
| 03 | parity-carry **phase-1** | 0 realized | depth-1 `rem` vselect; −64 valu absorbed |
| 01 | D3 gather port (tested) | 0 / +3 | `_d3_gather_tail=8` → 1211 on 1208 graph; **default off** |

Tail gap @ 1208: combined floor ≈ 1111.5 vs realized 1208 → **~96 cycles** windup/drain
packing loss (~8.7% inflation). Op-count drops shrink the floor; realized follows with lag
unless mask/offset are re-tuned.

---

## Active directions (ranked — op-count route)

| Priority | # | Direction | Est. valu | Scratch | Conf | Worktree |
|---|---|---|---|---|---|---|
| **1** | **12** | **p-space traverse** (store `p` not `idx`) | **−256** | **0** | medium-high | `explore/merged-floor` |
| 2 | 01 | D3 drain mux→gather + combine_tail re-sweep | −4…−8 | 0 | medium | `explore/merged-floor` |
| 3 | 03 | parity-carry **phase-2** d2/d3 (re-permuted tables) | −320 | **+256…768** | medium | `explore/03-round-structure` |
| 3b | 13 | **mem spill** for rem history (unlocks #03) | (enabler) | mem | low-med | TBD |
| — | 02 | K5-deferral | landed | — | — | `explore/02-hash-opcount` |
| — | 11 | dead-idx | landed | — | — | `explore/11-dead-code-idx` |

**Ceiling estimate** (all op-count wins + rebalancing): combined floor ≈ **1035**;
realized optimistic **1125–1150**, conservative **~1170**. Below that requires changing
the hash itself — #02 proved **K5 is the only deferrable constant** (others blocked by
multiplication nonlinearity).

---

## Deprecated / falsified directions

| # | Direction | Verdict | Why |
|---|---|---|---|
| **01** | exact-scheduler (CP-SAT) | **FALSIFIED** | Greedy ≤1 cycle from optimal; drain prize ≤3 cycles. **Byproduct kept:** drain-tail mux→gather (`_d3_gather_tail`) — port to merged-floor, re-sweep on 1208 graph. |
| **04** | modulo-pipeline | **DEPRECATED** | Same windup/drain target as #10; offset search already captured it. |
| **09** | data-layout / depth-interleave | **DEPRECATED** | Same; CP-SAT shows middle band triple-saturated. |
| **05** | cross-vector-share | **DEPRECATED** | flow not binding; overlaps #08. |
| **06** | regalloc-hazards | **DEPRECATED** (refutation only) | Rename-to-parallelize disproved; no unnamed op win. |
| **07** | load-engine-lut | **DEPRECATED** (self-refuted) | load floor below binding; gather-reduction marginal on 1208 graph. |
| **08** | flow-vselect | **LOW / mostly superseded** | §3.3 wrap hack dead (#11); depth-3 flow relief minor on 1208 graph. |
| **10** | autotuner | **LANDED (manual)** | Offset vector + combine mask found offline; SA still useful after each op drop. |

---

## Recommended execution order (new machine)

All steps on branch `explore/merged-floor`, commit after each `submission_tests.py` pass.

1. **#12 p-space traverse** — `p ← 2p+rem` muladd; gather `addr = fvp_p_d + p`; d1 cond = `p`.
   **Do not** naïvely use `p>>k` for d2/d3 mux bits (borrow mixing). Either materialize
   `idx_true = (2^d−1)+p` for mux rounds (+1 valu) or finish phase-2 table re-permute.
   Then **re-sweep** `COMBINE_HEAD/TAIL` + offset.
2. **#01 D3 gather tail** — `D3_GATHER_TAIL=6..8` × `COMBINE_TAIL` grid on 1208 graph.
3. **#13 mem spill** (if needed) — vstore/vload rem ring to mem; unlocks #03 phase-2.
4. **#03 phase-2** d2/d3 re-permuted parity tables — **−320 valu** after scratch solved.
5. After **every** op-count change: `sweep_headtail.py` + offset re-search.

```bash
# verify gate (every commit)
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py   # must print OK, CYCLES <= best
```

---

## Worktree map

```
vliw/                              # main repo; docs in directions/
explore/merged-floor/              # GLOBAL BEST 1208 — integration branch
explore/02-hash-opcount/           # K5-deferral (landed → 1215 alone)
explore/10-autotuner/              # offset search (landed → 1208)
explore/11-dead-code-idx/          # dead idx (landed → 1228 alone)
explore/03-round-structure/        # parity-carry phase-2 experiments
explore/01-exact-scheduler/        # CP-SAT archive + D3 gather origin
explore/{04,05,06,07,08,09}-*/     # deprecated archives
```

Setup on a fresh machine: `scripts/setup-worktrees.sh` (see `explore/README.md`).

---

## Direction files

| File | Status |
|---|---|
| [11-dead-code-idx.md](11-dead-code-idx.md) | landed |
| [02-hash-opcount.md](02-hash-opcount.md) | landed |
| [10-autotuner.md](10-autotuner.md) | landed (manual sweep) |
| [03-round-structure.md](03-round-structure.md) | phase-1 landed; phase-2 scratch-blocked |
| [12-pspace-traverse.md](12-pspace-traverse.md) | **active — try first** |
| [01-exact-scheduler.md](01-exact-scheduler.md) | falsified; byproduct noted |
| [04-modulo-pipeline.md](04-modulo-pipeline.md) | deprecated |
| [09-data-layout.md](09-data-layout.md) | deprecated |
| [05-cross-vector-share.md](05-cross-vector-share.md) | deprecated |
| [06-regalloc-hazards.md](06-regalloc-hazards.md) | deprecated |
| [07-load-engine-lut.md](07-load-engine-lut.md) | deprecated |
| [13-mem-spill.md](13-mem-spill.md) | proposed (unlocks #03) |

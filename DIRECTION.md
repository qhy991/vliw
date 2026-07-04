# Direction: Cross-Vector Redundancy at Shallow Depths

## 1. Direction name + one-line thesis

**Name:** Collapse the shallow-depth node-acquisition muxes (attack the flow floor), NOT the hash.

**Thesis:** The hash itself is algebraically **unsharable** across vectors/lanes — `val` is full-entropy per element from round 0, and every hash sub-expression depends on `val`, so no cross-vector arithmetic can be hoisted. But the *node-acquisition* step at shallow depths (depth-1/2/3 `vselect` muxes) is the one place that touches genuinely low-cardinality shared data (2/4/8 distinct node values), and it **single-handedly generates the entire 736-cycle flow-engine floor**. Restructuring how those muxes are computed cross-vector is the only surviving cross-vector lever, and it attacks a floor (flow=736) plus the tail scheduler slack, not the saturated middle.

---

## 2. Why this could beat 1230 (quantitative, tied to verified floors)

### 2.1 First, the honest kill: hash sharing is impossible

Rigor demanded by the brief. At **round 0**, `inp.values` are 256 independent random 32-bit ints (`Input.generate`, `problem.py:435`). Depth-0 does `val = myhash(val ^ tree[0])`. `tree[0]` is a **shared broadcast** (`nb0`), but `val` is per-element, so `val ^ nb0` is per-element. `myhash` (`problem.py:449-464`) is a composition of stages each of which is a bijection in `a` (`a -> (a+K)⊕(a<<s)` etc.), so distinct inputs give distinct outputs and the full-entropy per-element distinctness is preserved through all 16 rounds. **Therefore every hash sub-term (`multiply_add`, the `t1/t2` pairs at `perf_takehome.py:419-427`, the combines) is per-element and cannot be shared, hoisted, or deduplicated across the 32 vectors.** The node broadcasts that *are* shared (`nb0..nb14`, `d3_0..d3_7`) are **already** hoisted once into setup (`perf_takehome.py:544-592`, verified: `broadcast_scalar` appears only in setup, zero `vbroadcast` in the body). So the naive reading of this direction — "share the hash at shallow depths" — is a confirmed dead end. Do not spend time there.

### 2.2 The surviving lever: the flow floor is 100% shallow-depth muxes

Here is the non-obvious quantitative finding. The flow engine has **1 slot/cycle** and the notes give `flow: 736/1 = 736`. I traced where all 736 flow ops come from (`_emit_vec_round`, depth branches):

| round | depth | flow (vselect) ops/vec | ×32 vec |
|---|---|---|---|
| r1, r12 | 1 | 1 | 64 |
| r2, r13 | 2 | 3 | 192 |
| r3, r14 | 3 | 7 | **448** |
| r10 | 10 (bottom wrap) | 1 | 32 |
| **total** | | | **736** |

**The flow floor is *exactly* the shallow-depth muxes.** Depth-3 alone (rounds 3, 14) contributes 448 flow ops = a hard 448-cycle floor if flow ever binds; depth-2 adds 192. These muxes were introduced (per OPTIMIZATION_NOTES §3, "re-gather replacing depth-2/3 muxes" is dead) *specifically to move node-acquisition off the load engine* — and that trade was correct for load. But it dumped the cost onto flow, and **the low-cardinality shared structure of the node values at these depths is precisely what makes a cheaper cross-vector formulation conceivable.**

At depth 3, each of the 32 vectors independently runs a 7-vselect tournament over the **same 8 broadcast node values** (`d3_0..d3_7`), selected by that vector's own `idx` bits. The *node table* is shared (8 values); only the *selection index* (`idx & {1,2,4}`) is per-element. The redundancy is: **32 vectors × 7 vselects all navigating the identical 8-entry table.**

### 2.3 How many cycles are on the table

Flow is not the binding floor globally (alu+valu combined = 1174 binds the middle), so shaving flow ops does **not** directly move the 1174 floor. The gain is **indirect and lives in the tails**, which is exactly where OPTIMIZATION_NOTES §3 localizes the 75-cycle gap over 1174 ("windup/drain... too few vectors in flight to fill both engines"). The mechanism:

- Depth-1/2/3 rounds emit **zero load ops** (verified: profile shows `load=0` for d0-d3). So during the schedule regions dominated by shallow-round work, the load engine (2 slots) and store engine are ~idle, and flow is *heavily* loaded (7 vselects/vec at d3). If the depth-3 mux is reformulated to use **fewer flow ops** (e.g. 7 → 3–4) by exploiting the shared table, the freed flow slots and the valu ops that currently wait behind serialized `vselect` chains (each L2 vselect depends on two L1 vselects — a depth-3 *dependency chain* of length 3 inside each vector) shorten the critical path in the windup, letting more vectors get in flight earlier.
- Concretely: if depth-3 drops from 7→4 flow/vec, that removes 3×32×2 = 192 flow ops (448→256). If depth-2 drops 3→2, removes 64. Total flow floor 736 → ~480. Whether that converts to cycles depends on the scheduler, but the theoretical tail headroom that §3 identifies as recoverable is ~19 cycles already realized (1249→1230) with ~56 more toward the 1174 floor **if** the tails can be filled — and the tails are filled by getting vectors in flight faster, which is gated by the shallow-round dependency chains this idea shortens.

**Estimated reachable:** optimistic 1195 (recover ~half the remaining tail gap by de-serializing shallow rounds), likely 1225–1232 (flow was not binding, so most of the win is scheduler luck). **This is a low-confidence, high-variance lever** — see §5.

---

## 3. Mechanism: exactly what changes in perf_takehome.py

All changes are in `KernelBuilder._emit_vec_round` (`perf_takehome.py:321-449`) and its setup (`perf_takehome.py:548-608`). The ISA ops available (from `problem.py` `flow`/`valu`/`alu` handlers) that matter: `vselect` (flow, `problem.py:308`), `v_alu` `&`/`<<`/`>>`/`+`/`<` (valu), `multiply_add`, and — critically — there is **no lane-shuffle / permute / gather-from-scratch** op, so all cross-vector sharing must go through broadcast (`vbroadcast`, one scalar → 8 lanes) or contiguous `vload`/`vstore`. This constrains the design hard.

### 3.1 Primary change: index-arithmetic node selection instead of vselect tournament (depth 3)

Today depth-3 (`perf_takehome.py:358-395`) does a 7-vselect binary tournament over 8 broadcasts, driven by `idx&1, idx&2, idx&4`. Replace the *tournament* with **arithmetic address synthesis + a single flow op or zero flow ops**:

- Observe `idx ∈ {7..14}` at depth 3. The node value is `tree[idx]`. The current code avoids the 8 scalar loads because loads were the old bottleneck. But the muxes cost 7 flow. **Alternative A (fewer vselects via 2-level instead of 3-level):** precompute, in setup, four *pair-broadcasts* is impossible (no per-lane distinct broadcast). Instead reduce tournament depth by folding the L1 layer arithmetically: since the 8 values are constants known at build time, compute `node = base + Σ bit_k · (val_k − base)` — but that requires per-lane `val_k` which aren't available without a gather. So Alternative A must stay vselect-based; the realistic reduction is **7→ (still 7)** unless we change the selection substrate.
- **Alternative B (the real one): partial re-gather ONLY at depth 3, ONLY in the schedule regions where load is idle.** OPTIMIZATION_NOTES marks "re-gather replacing depth-2/3 muxes" as dead (d3→1380) — but that test replaced *all* muxes globally. The refined hypothesis: depth-3 rounds are r3 and r14. r3 is in the **windup** (load idle), r14 is near the **drain**. A gather is `1 v_alu (+) + 8 load` = 8 load slots but **0 flow**, vs the mux's `3 valu + 7 flow`. In a load-idle windup, trading 7 flow (1 slot/cyc, serialized, 3-deep dependency chain) for 8 load (2 slots/cyc, no chain, load engine empty) could **shorten the windup critical path** even though it lost the global load-floor argument. The change: add a per-combine-style counter/flag so depth-3 node-acq picks `gather` when the vector's emit position falls in the windup band (first ~`_d3_gather_head` d3-instances) and `mux` otherwise. This mirrors the existing head/tail `_combine` machinery (`perf_takehome.py:301-313`) exactly — a correctness-free scheduling knob.

### 3.2 Data structures / new fields

Add to `KernelBuilder.__init__` (near `perf_takehome.py:230-233`), mirroring the `_combine_head/_combine_tail` pattern:
```python
self._d3_no = 0            # depth-3 node-acq instances emitted this rotation
self._d3_gather_head = 0   # first N d3-instances use gather (load-idle windup); rest use mux
```
Reset in `gen_body` (`perf_takehome.py:683`) alongside `self._combine_no = 0`. In the depth-3 branch, dispatch on `self._d3_no < self._d3_gather_head` → emit the existing `else` gather block (`perf_takehome.py:396-400`) instead of the mux, incrementing `self._d3_no`.

### 3.3 Secondary change: depth-2 mux reduction (3 flow → 2 flow)

Depth-2 (`perf_takehome.py:339-357`) uses 3 vselects for a 4-way mux. The `hi = (4 < idx)` and `odd = idx&1` are computed, then 3 vselects. A 4-way select over 4 constant broadcasts can be done as **2 vselects** if we combine the two inner selects: currently it does inner_lo, inner_hi, then outer — but the outer select reads `node` (inner_hi) and `mtmp` (inner_lo). That is already the minimal 3 for a balanced 4-way tree with vselect (log2(4)=2 levels but the first level needs 2 selects → 2+1=3). To hit 2, replace one level with **arithmetic**: `node = odd ? T[hi?5:3... ]` — the odd bit picks between two constants that differ; encode as `node = cst_a + odd·(cst_b − cst_a)` per branch using `multiply_add` (valu) so only the `hi` select stays on flow. Net: **3 flow → 1 flow + ~2 valu** per vec at d2. Since d2 rounds (r2,r13) are also shallow/valu-crowded, this is a flow→valu rebalance and must be gated the same head/tail way; test whether valu can absorb it.

### 3.4 Scratch budget

Verified headroom: per-vector scratch = 32 vectors × 4 vecs × 8 = 1024 words of `SCRATCH_SIZE=1536`; ~200 words of consts/broadcasts/mtmp groups; **~300 words free**. A partial-gather variant needs no new per-vector scratch (reuses `node`/`addr`). A pair-broadcast table for d3 (if pursued) would need ≤ 8 more vecs = 64 words — fits.

---

## 4. Day-1 experiment (smallest thing to validate/kill fast)

**Goal:** determine in one build whether trading depth-3 flow for load in the windup helps at all, before any elaborate arithmetic reformulation.

Step 1 — add the `_d3_no / _d3_gather_head` fields (§3.2) and the dispatch in the depth-3 branch. Set `_d3_gather_head = 8` (roughly one windup band of d3-instances). This is ~15 lines mirroring `_combine`.

Step 2 — measure. Because `n_groups==1 ⇒ cycles == len(kb.instrs)`, count bundles without running the machine (fast: build is ~200s, running adds little but skip it for the sweep):
```bash
python -c "
from perf_takehome import KernelBuilder
kb = KernelBuilder(); kb.build_kernel(10, 2047, 256, 16)
print('CYCLES:', len(kb.instrs))"
```
Baseline to beat: **1230**.

Step 3 — sweep `_d3_gather_head ∈ {0,4,8,16,32,64}` (0 = unchanged control, must reprint 1230). Because each full build is ~3.5 min (rotation search over K=32 dominates), run the sweep in the background and, to iterate faster, **temporarily pin the rotation** (`for rot in range(K)` → `for rot in [0]` at `perf_takehome.py:719`) to cut build to ~7s; use pinned-rot deltas as the signal, then confirm the winner with the full rotation search.

Step 4 — the moment any config prints `< 1230`, validate correctness with the full machine on unseeded input:
```bash
python tests/submission_tests.py   # must print OK and CYCLES: <n>
```
**Kill criterion:** if the entire `_d3_gather_head` sweep (with full rotation search) is `≥ 1230`, the "flow→load in windup" hypothesis is dead; fall back to the §3.3 depth-2 flow→valu rebalance as a second, cheaper probe. If that too is `≥ 1230`, the direction is dead — flow simply never binds and de-serializing shallow muxes doesn't fill the tails. Document and stop.

---

## 5. Risks & likely failure modes (honest)

1. **Flow is not the binding floor (highest risk).** The middle [200-1000] is alu+valu jointly saturated at ~100% (OPTIMIZATION_NOTES §3); flow at 736 is well under 1230. Reducing flow ops only helps if flow is *locally* binding in the windup/drain, which is unproven. Most likely outcome: flow slots free up but the schedule length is unchanged because valu/alu still bind → **no improvement, prints ~1230.**
2. **The re-gather regression is documented.** OPTIMIZATION_NOTES §3 explicitly killed "re-gather replacing depth-2/3 muxes" (d3→1380, d2→1421). My variant is narrower (partial, windup-only, gated) so it is *not* the same experiment — but it shares the failure mechanism: gathers reintroduce **load-latency dependency stalls** (the `val^node→hash` chain waits on the load), which is exactly why the muxes exist ("muxes keep node resident, avoiding load-latency stalls"). If load latency > 0 in the sim, even windup gathers may stall the hash chain. **Check the sim's load model first** (`Machine.load`, `problem.py:269` — effects apply end-of-cycle, so a load result is available next cycle; a dependent op in the same bundle can't read it). This 1-cycle producer→consumer gap is the stall.
3. **Depth-2 arithmetic reformulation (§3.3) moves cost to valu**, which is *more* contended than flow. Likely regresses unless confined to load-idle tail bands.
4. **Build cost makes the sweep slow** (~3.5 min/full build). Mitigation: pin rotation for the delta signal (§4 step 3). But pinned-rot deltas may not survive the full rotation search (packing noise, OPTIMIZATION_NOTES §5) — a pinned-rot win of 2 cycles could vanish. **Any sub-1230 result must be confirmed with full rotation search AND correctness.**
5. **Packing noise floor.** OPTIMIZATION_NOTES §5 warns the last few cycles are scheduler-packing luck (1230 vs 1233 neighbors). A "win" of 1-3 cycles here is likely noise, not structural. Only a ≥8-cycle drop should be believed as real.

---

## 6. Expected payoff + confidence + effort

- **Expected cycles:** optimistic **1195** (if de-serializing the depth-3 mux chain lets the windup fill both engines ~40 cycles sooner); likely **1225–1232** (flow doesn't bind; net wash or noise-level change). Point estimate: **~1228, i.e. marginal.**
- **Confidence it beats 1230 at all: LOW.** The algebraic core of this direction (hash sharing) is provably dead; the surviving flow-floor lever attacks a floor that is not globally binding, so the payoff depends entirely on unproven local windup dynamics. This is the honest assessment the brief demands: cross-vector redundancy is *mostly a mirage here* because full-entropy `val` defeats sharing, and the one real shared structure (node tables) is already broadcast-hoisted.
- **Effort:** Day-1 probe ~0.5 day (15 lines + sweep). Full depth-2/3 arithmetic reformulation ~1.5 days. Total **~2 days** — but front-loaded so the kill criterion (§4) fires within the first half-day. **Recommend gating further investment on a ≥8-cycle Day-1 signal.**

---

## 7. Dependencies / prerequisites

- **No new library, no test changes** (HARD RULE: never touch `tests/` or `frozen_problem.py`). All edits confined to `KernelBuilder._emit_vec_round`, its setup, and `__init__` in `perf_takehome.py`.
- **Scratch budget:** ~300 free words available (verified: 1024/1536 used by per-vector state); the partial-gather variant needs zero new scratch, the pair-broadcast variant ≤64 words. No refactor needed.
- **Load-latency model check (prerequisite before §3.1 Alternative B):** confirm in `Machine.step`/`load` (`problem.py:269-286`, `352-397`) that a load's result is only visible the *next* cycle (writes applied after all reads, end of bundle) — this determines whether windup gathers stall the hash chain and is the single fact that most likely kills the gather variant.
- **Iteration-speed prerequisite:** a scratch harness that pins `rot` (`perf_takehome.py:719`) to make builds ~7s instead of ~3.5min for the sweep; revert to full rotation search for any confirmed candidate.
- **Cross-check with sibling directions:** this lever competes for the *same tail slack* as the existing head/tail `_combine` rebalance (§4.1 of OPTIMIZATION_NOTES). If a sibling lane is also refilling the windup/drain, gains are non-additive — coordinate so the `_d3_gather_head` and `_combine_head/tail` sweeps are tuned *jointly*, not independently (their response surfaces interact).

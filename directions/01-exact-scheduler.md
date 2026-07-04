# Direction: Near-Optimal Scheduler via CP-SAT Modulo-Resource Scheduling over Macro-Round Windows

## 1. Direction name + one-line thesis

**Windowed CP-SAT resource-constrained scheduler with joint engine assignment.**

Replace the single greedy list-scheduler pass (`perf_takehome.py:139-201`, the `run(key)` closure inside `Scheduler.schedule`) with an exact/near-exact solver (OR-Tools CP-SAT) that solves resource-constrained scheduling *and* the alu/valu engine-assignment knob *jointly*, decomposed into overlapping macro-round windows so the 23,420-op body stays tractable. Thesis: the greedy scheduler is provably leaving cycles on the table only in the tails (verified below), and the drain tail's problem is a *packing/assignment* problem the greedy list scheduler cannot solve because it commits engine assignment at emit time and never backtracks.

## 2. Why this could beat 1230 (quantitative, tied to verified floors)

I re-measured the winning rotation directly (instrumented `Scheduler.schedule`, batch=256 → n_groups=1 → cycles == len(bundles)). Numbers below are **measured, not derived**:

**Body = 23,420 ops → 1230 bundles.** Per-engine op counts (this rotation, post head/tail rebalance + depth-0 fold):
- `valu`: 7022 ops → floor 7022/6 = **1170.3**
- `alu`: 13456 ops → floor 13456/12 = **1121.3**
- `load`: 2174 ops → floor 2174/2 = **1087.0**
- `flow`: 736 ops → floor **736.0**
- of the valu ops, exactly **1952 are `multiply_add`** (locked to valu, no alu equivalent); the other 5070 valu ops + all 13456 alu ops are the flexible/movable population.

**Combined alu+valu throughput floor** (the real floor per OPTIMIZATION_NOTES §2): treating every alu op as flexibly re-packable as 1/8 of a valu slot, vec-equivalent work = 7022 + 13456/8 = 8704, and each cycle offers 6 valu + 12 alu = 7.5 vec-equivalents → **1160.5**. Adding back the reality that `multiply_add` (1952) and `flow` vselects (736) are engine-locked and serialize, the achievable combined floor sits at **~1174** (matches the notes). **Current 1230 is 56 cycles above this floor.**

**Where the 56 cycles live** (measured bundle occupancy, this is the key evidence):

| window | bundles | alu % | valu % | load % | flow/cyc |
|---|---|---|---|---|---|
| windup [0-100] | 100 | 97.7 | 85.2 | 63.0 | 0.57 |
| windup [100-200] | 100 | 100.0 | 96.5 | 86.0 | 0.83 |
| **middle [200-1000]** | 800 | 98.9 | **99.5** | **100.0** | 0.56 |
| pre-drain [1000-1130] | 130 | 95.6 | 96.7 | 81.5 | 0.67 |
| **drain [1130-1230]** | 100 | **8.0** | 67.2 | 32.0 | 0.57 |

Two hard conclusions:
1. **The middle [200-1000] is triple-saturated** (alu ~99%, valu 99.5%, load 100%). There is *nothing* for a scheduler to win here - it is a genuine resource floor. A better scheduler must not touch it (matches the "don't load the both-bound middle" finding).
2. **The drain tail [1130-1230] is where ~50 of the 56 cycles hide.** alu is 8% idle-to-empty while valu runs 67%. The drain histogram shows it is dominated by *engine-locked serial hash work*: 141 valu `^`, 91 `multiply_add`, 167 other valu ops (`>>`/`+`/`<<`/`&`/`%`), 57 flow vselects, 64 loads. The alu is empty **because there are too few independent vectors left in flight to generate flexible XORs to fill it**, and the remaining work is the strictly-serial 6-stage hash chain of the last vectors (`_emit_vec_round`, `perf_takehome.py:419-427`: muladd → xor/shift → combine, ×3, each stage depends on the prior).

**The theoretical prize:** if the drain's serial chains could be interleaved so 6 valu slots stay full, the drain compresses from ~100 bundles toward its own valu floor. The drain contains ~91 muladd + 141+167 valu-flex + ... The greedy scheduler drains one-vector-at-a-time-ish; an optimal modulo scheduler that overlaps the last K vectors' final rounds could plausibly recover **20-50 cycles**, landing 1180-1210. This is the *only* region with slack, and it is a packing/assignment problem - exactly what CP-SAT is built for and greedy list-scheduling with a fixed priority key provably cannot solve (the (step,rot,key) space is exhausted at 1249; the tail rebalance heuristic got 1230; neither can reorder+reassign engines with lookahead).

## 3. Mechanism: exactly what changes in perf_takehome.py

**Scope of edits:** only `class Scheduler` (`perf_takehome.py:72-201`) and the plumbing in `KernelBuilder.emit`/`gen_body`/`build_kernel` that calls it (`:259-264`, `:679-726`). The op-DAG construction (`deps` building at `:97-117`) is correct and reused verbatim - do not touch it, it encodes RAW/WAR/WAW correctly and is the ground truth.

### 3.1 New solver class `CpSatScheduler` (drop-in for `Scheduler`)

Keep `Op` (`:59-69`) and the `deps`, `succ`, `hgt` computation (`:97-137`) unchanged - reuse them. Replace only the greedy `run(key)` body with a CP-SAT model.

**Decision variables (per window, see 3.3):**
- `start[i]` ∈ [est_i, lst_i]: integer bundle index each op is placed in. ASAP/ALAP bounds (`est`=longest dep path from window start via `hgt`-style forward pass, `lst`=window_len − backward `hgt`) prune the domain hard.
- `eng[i]` ∈ {0=native, 1=alt}: **only for flexible ops.** A vector XOR combine (`_combine`, `:301-313`) currently chooses engine at emit time; instead emit it as ONE abstract op flagged `flexible=True` carrying *both* costs (1 valu slot, or 8 alu slots). `eng[i]` picks. `multiply_add`, `vselect` (flow), `vload`/`vstore`, `vbroadcast` are non-flexible (fixed engine).

**Constraints:**
- Precedence: `start[j] >= start[i] + 1` for every edge `i→j` in `deps[j]` and `ops[j].after` (latency 1 cycle; the sim has no multi-cycle latency - effects land end-of-cycle, `problem.py:388-391`). Note: same-bundle producer→consumer is illegal because writes commit at cycle end, so use strict `+1`. This matches greedy's `sched[d] >= cur` check (`:160-167`).
- Cumulative resource per engine per bundle via `AddCumulative` or, simpler and exact here, per-bundle `AddReservoir`/interval-free channeling: for each bundle b and engine e, `sum over i of (start[i]==b AND eng_of_i==e) * slot_cost <= SLOT_LIMITS[e]` (`problem.py:48-55`: alu 12, valu 6, load 2, store 2, flow 1). Implement with boolean `is_at[i,b]` = (start[i]==b) reified, then `AddCumulative` over optional intervals is the idiomatic CP-SAT form: one optional interval per op of duration 1, demand = slot cost, capacity = slot limit, with the flexible-engine ops modeled as **two optional intervals (valu-variant, alu-variant) gated by `eng[i]`, exactly one present.**
- Objective: `minimize makespan` = max(start[i]) over window (or, for a fixed-length window, minimize a soft count of the last non-empty bundle).

**Correctness invariant:** CP-SAT only reorders and reassigns engines subject to `deps`/`after`; since those edges are the complete hazard set the greedy scheduler also honors, any feasible CP-SAT schedule produces bit-identical memory. The engine flip (valu XOR vs 8× alu XOR) is arithmetically identical (OPTIMIZATION_NOTES §1.2). **No new correctness surface.**

### 3.2 Emission change to expose the engine knob to the solver

In `_combine` (`:301-313`) stop deciding valu-vs-alu at emit time. Instead emit a single tagged op: extend `Op.__slots__` (`:60`) with `flexible` and `alt` fields, and have `_combine` call a new `self.v_alu_flex("^", dest, a, b)` that records one op with `engine="valu", slot=("^",dest,a,b)` plus `alt=("alu", [8 per-lane scalar slots], reads/writes)`. The solver reads `.flexible`/`.alt`; the greedy fallback (3.4) just uses `.engine`. This moves the head/tail heuristic (`_combine_head`/`_combine_tail`, `:230-233`, `:310`) *into the solver as a free variable* - delete the heuristic once the solver wins.

### 3.3 Decomposition (the crux - 23k ops is far too big for one solve)

Do **not** solve the whole body. CP-SAT will not close 23,420 ops with cumulative constraints in reasonable time. Two-tier strategy:

- **Tier A (cheapest, do first): solve ONLY the drain tail.** Run the existing greedy scheduler to place bundles [0 .. ~1120] unchanged (the saturated middle is optimal already). Take the *unscheduled residual* - the ops whose greedy placement is ≥ ~1120 - which is a few thousand ops forming the last vectors' final rounds, and hand *only those* to CP-SAT with a makespan objective. This is the highest-value, lowest-risk cut: it attacks exactly the slack region and keeps the solve small (~2-4k ops, and mostly a narrow dependency front).
- **Tier B (if Tier A wins): overlapping macro-round windows.** Partition emit order into windows of ~W diagonals (the `diag` loop at `gen_body`, `:689`). Solve window k with the tail of window k−1 frozen as fixed "already placed at bundle t" facts (fixed-start ops become resource occupancy the solver must schedule around). Slide with overlap so cross-window pipelining survives. Window size W tuned so each solve is ≤ ~1500 ops / ≤ ~200 bundle span (CP-SAT handles this in seconds-to-minutes with `max_time_in_seconds`).

**Build-time budget:** `build_kernel` already does 32 full greedy builds for the rotation search (`:719-723`, measured). A CP-SAT solve of the *whole* body per rotation is infeasible. So: keep greedy for the rotation search to pick the best `rot`, then run CP-SAT **once** (Tier A) on that single best rotation's residual. This keeps total build time to 32 greedy builds + 1 bounded CP-SAT solve.

### 3.4 Fallback / safety

CP-SAT is wrapped: `solver.parameters.max_time_in_seconds = <budget>`; if status is not OPTIMAL/FEASIBLE, or if the produced schedule is *longer* than greedy, **discard it and keep the greedy bundles**. So the worst case is "no change, 1230." Guard the whole thing behind a flag so `import ortools` failure (see §7) silently falls back to greedy.

## 4. Day-1 experiment (smallest thing that validates or kills it fast)

**Goal: prove CP-SAT can beat greedy on the drain tail alone, before building any windowing machinery.**

Step 1 - extract a real drain subproblem (no solver yet):
```bash
cd /Users/haiyan-mini/Agent4Kernel/vliw
# Instrument Scheduler.schedule to dump the winning rotation's ops + greedy bundle
# assignment to a pickle (ops with deps/after, engine, slot cost, and greedy start).
python3 -c "import perf_takehome as P; ...  # monkeypatch capture as I did in analysis"
```
Step 2 - build a standalone `cpsat_probe.py` (scratch file, NOT in tests/) that loads the pickle, takes the residual ops with greedy start ≥ 1120 (~110 bundles, ~2k ops), builds the CP-SAT model of §3.1 with `AddCumulative` optional intervals + the `eng[i]` flexible-engine variables, and minimizes makespan with `max_time_in_seconds=120`.

**Kill/validate criterion:** compare CP-SAT makespan of the residual against greedy's 110-bundle span.
- If CP-SAT returns a makespan ≤ ~90 (≥ ~20-cycle win on the tail) → **validated**, proceed to integrate as Tier A.
- If CP-SAT proves OPTIMAL == greedy's span (or within 2-3) → **killed**: the drain is dependency-limited, not scheduler-limited, and no scheduler can help. This is the honest fast-kill.

Measure the true end-to-end number after integration with the frozen-safe path:
```bash
python3 tests/submission_tests.py    # must print OK and CYCLES: <n>; n<1230 = win
# and the fast bundle-count proxy during iteration (no correctness run needed):
python3 -c "from perf_takehome import KernelBuilder; kb=KernelBuilder(); kb.build_kernel(10,2047,256,16); print('CYCLES',len(kb.instrs))"
```

**Environment confirmed today:** Python 3.14.3; `pip install ortools` succeeds (ortools 9.15.6755, wheel exists for 3.14); `from ortools.sat.python import cp_model` imports and `CpModel()` constructs. So the tool is available.

## 5. Risks & likely failure modes (honest)

1. **The drain is dependency-bound, not schedule-bound (highest risk).** The drain histogram is dominated by engine-*locked* serial hash ops (91 muladd, 57 flow vselect, 141 valu XOR that could go to alu but whose *producers* are serial). If the 6-stage hash chain (`:419-427`) of the last vectors is a true critical path with no independent work to interleave, CP-SAT finds the same span and proves it optimal → **0 cycles won.** OPTIMIZATION_NOTES §3 already found only 17/1249 bundles are pure dep-stalls and "缩链无收益" - a real warning this may be dep-limited. The Day-1 experiment exists specifically to detect this in <1 day.
2. **Middle is genuinely saturated (confirmed):** alu 98.9% / valu 99.5% / load 100%. No scheduler wins there. The prize is strictly the tails, capping the upside near the 56-cycle gap and realistically well under it.
3. **CP-SAT doesn't scale / doesn't close.** Even 2k ops with cumulative + reified start-position booleans can blow up. Mitigations: tight est/lst domains from `hgt`; `AddCumulative` optional intervals (native propagator) rather than O(n·bundles) reified booleans; `max_time_in_seconds` cap with FEASIBLE-accept.
4. **Windowing (Tier B) loses cross-window pipelining.** The greedy scheduler's whole strength is co-scheduling vector A's gather with vector B's hash across the entire stream (`perf_takehome.py:19-27` docstring). Hard window boundaries can *destroy* this and regress. Mitigation: overlap windows and freeze boundary ops as fixed occupancy, not as hard cuts. If Tier A already loses, skip Tier B entirely.
5. **Build-time explosion in the rotation search.** Never run CP-SAT inside the 32-rotation loop. Greedy picks `rot`; CP-SAT runs once.
6. **Determinism / reproducibility.** CP-SAT is deterministic given fixed `random_seed` and single worker (`num_search_workers=1`), but multi-threaded search is not. Pin `parameters.num_search_workers=1` and `random_seed` so the emitted cycle count is stable across runs (the submission must reproduce).

## 6. Expected payoff & effort

- **Payoff:** if the drain is packable, **20-50 cycles → 1180-1210.** If additionally Tier B recovers windup slack (windup alu is already 97-100%, so little there), maybe a few more. Realistic target **~1200; optimistic ~1180.** Beating the ~1174 combined floor is **not** possible with this direction (it is a *scheduler*, not an op-count reducer) - 1174 is the wall.
- **Confidence: low** that it beats 1230 at all. The dominant risk (#1) is real and the notes' prior negative results on chain-shortening point the same way. But the Day-1 experiment is a cheap, decisive test, and the *upside is structural* (not packing luck like the 1230 tail-tuning), so it is worth one exploration lane.
- **Effort:** Day-1 probe ~0.5-1 day. If validated: Tier A integration + frozen-safe fallback + reproducibility pinning ~2-3 days. Tier B (only if Tier A wins) ~2-4 days. Total **1 day to kill, ~1 week to fully exploit.**

## 7. Dependencies / prerequisites

- **OR-Tools:** `pip install ortools` (confirmed working on this box: Python 3.14.3, ortools 9.15.6755). **This adds an import dependency to `perf_takehome.py`** - it MUST be optional: `try: from ortools.sat.python import cp_model; except ImportError: cp_model=None`, and the scheduler falls back to the existing greedy path when unavailable, so a grader without ortools still gets a correct 1230. Verify the grader environment can `pip install ortools` or accept the fallback; if the grader forbids new deps, this entire direction is blocked - **check this before investing.**
- **No scratch-space budget needed** (scheduler is compile-time only; does not touch runtime scratch, `SCRATCH_SIZE=1536`).
- **Refactor prerequisite:** expose the flexible engine knob as a solver variable - extend `Op.__slots__` (`:60`) with `flexible`/`alt`, add `v_alu_flex` to `KernelBuilder`, route `_combine` (`:301-313`) through it. This is a self-contained ~30-line refactor that also *removes* the `_combine_head`/`_combine_tail` heuristic (`:230-233`) once the solver subsumes it.
- **Determinism pin:** `solver.parameters.num_search_workers = 1` and a fixed `random_seed` so cycle count is reproducible for submission.
- **HARD RULE respected:** all edits confined to `perf_takehome.py`; `tests/` (incl `frozen_problem.py`) untouched; correctness validated on unseeded random inputs via `tests/submission_tests.py`.

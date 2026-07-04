# Direction: Scratch-as-op-count — spend registers to cut the combined ALU+vALU floor, not to break false deps

> **Working dir:** `/Users/haiyan-mini/Agent4Kernel/vliw` · **Target file (only editable):** `perf_takehome.py` · **Current best:** 1230 cycles (fixed shape `forest_height=10, rounds=16, batch=256`, `n_groups=1` ⇒ `cycles == len(kb.instrs)`).

---

## 1. Direction name + one-line thesis

**Name:** *Scratch-as-op-count.* Repurpose the register/scratch budget as an **op-count reducer**, not a **false-dependency breaker**.

**Thesis (one line):** The 1230-cycle schedule is throughput-bound, not serialization-bound — its critical path is length **2** and removing *all* WAR+WAW edges makes it **longer** — so the only way scratch allocation buys cycles is by using the ~65 free words to keep values resident / hoist invariants / fuse recompute so that fewer ALU+vALU ops are issued, lowering the ~1174 combined floor that actually gates the middle.

---

## 2. Why this could beat 1230 (quantitative, tied to measured floors)

### 2.1 The assigned premise was tested and **falsified** — record this before spending days

The task brief hypothesized that reused scratch (`node`, `addr`, the `mtmp` groups) creates WAR/WAW edges that serialize independent cross-vector ops and lengthen the schedule. I built the exact winning-rotation op stream (23 420 ops) and ran a counterfactual on the *same* greedy list scheduler:

| Dep set fed to scheduler | Resulting schedule length |
|---|---|
| All edges (RAW+WAR+WAW) — the real build | **1217** |
| RAW only (drop WAR+WAW → "infinite registers") | **1236** |

- Edge census: `RAW=101469, WAR=81592, WAW=76984`.
- **Critical path length = 2** whether or not false deps are kept. There is essentially *zero* true dependency-chain serialization to recover: the hash's 6 stages are per-vector short, and with 32 vectors in flight the DAG is almost entirely wide, not deep.
- Removing false deps is **−19 cycles of *negative* headroom**: the WAR/WAW edges actually *help* the greedy scheduler by pruning its ready-set toward a tighter packing. Handing it more freedom makes its greedy choices worse.

> **Conclusion that reshapes the whole lane:** "give temps dedicated registers to break false dependencies" is a **dead end as stated** — it cannot shorten a schedule whose critical path is 2 and whose bottleneck is engine slots. Do **not** spend days adding renamed temps hoping the scheduler packs tighter; the counterfactual says it packs *looser*.

### 2.2 What is actually gating — the combined throughput floor

Per-region engine occupancy of the real 1230-cycle program (measured):

```
[   0-  60] windup : alu 74%  valu 72%  load 97%  flow 17%
[  60- 150]        : alu 100% valu 91%  load 48%  flow 86%
[ 150-1050] middle : alu  99% valu 99%  load 100% flow 58%   <- jointly saturated
[1050-1150]        : alu  88% valu 96%  load 69%  flow 74%
[1150-1230] drain  : alu   9% valu 75%  load 40%  flow 62%
```

Engine op-counts (this exact build): `alu 13456 (floor 1122), valu 7022 (floor 1171), load 2174 (floor 1087), flow 736 (floor 736)`. The `v_alu`/`v_alu_scalar` knob lets a vector op count as 1 vALU slot **or** 8 ALU slots, so the real floor is the **combined** capacity:

```
per bundle = 6 vALU + 12 ALU/8 = 7.5 vector-op-equiv
fixed-on-vALU (multiply_add): 3 muladd/vec x 32 vec x 16 rounds = 1536, minus depth-0 folds
=> combined floor ≈ 1174   (OPTIMIZATION_NOTES §2, consistent with per-engine 1171/1122)
```

The middle [150-1050] is at 99/99/100% — **no packing slack there**. The gap over 1174 lives in windup+drain, but §2.1 proved that gap is *not* reclaimable by allocation (it's "no work left to issue", not "work blocked by false deps"). Therefore the **only** durable win is to **push the 1174 floor down by issuing fewer ALU+vALU ops per vector-round**, which shortens the saturated middle 1:1.

**Cycles theoretically on the table:** every vector-op-equiv removed from the steady state saves `32 vec × 16 rounds / 7.5 = ~68 cycles per op-per-vec-round` if it lands in the saturated middle. Even a fractional reduction (e.g. removing 1 vALU op on the 11 non-depth-0/1 rounds only) is worth ~20-40 cycles. Getting to the 1174 floor from 1230 is 56 cycles; beating it requires an actual op-count cut below the current arithmetic.

### 2.3 The residual, defensible allocation lever

Scratch *can* still help, but only in service of §2.2, in three concrete ways — each one **removes ops**, not edges:

1. **Keep per-vector invariants resident** so they are computed once (setup) instead of per round. Any sub-expression that is constant across all 16 rounds of a vector but currently recomputed each round is `32×(rounds−1)` redundant ops. (Candidate scan in §3.)
2. **Precompute-and-store the depth-schedule constants** (e.g. the `& 1`, `& 2`, `& 4` bit-extracts in the depth-2/3 muxes reuse `addr` and recompute per round; if the *condition vector* for a vector at a given depth is invariant it can be hoisted).
3. **Widen `mtmp` groups only if it reduces the vALU/flow op it feeds** — NOT to break WAR (that's refuted); NUM_MTMP_GROUPS is already swept to 3 as optimal, so this is a distant third.

---

## 3. Mechanism: exactly what changes in `perf_takehome.py`

All work is in `KernelBuilder` (`perf_takehome.py:212`). The scheduler (`Scheduler.schedule`, `:73`) and its dep model (RAW `:105`, WAW `:111`, WAR `:116`) are **left untouched** — §2.1 shows touching them via register renaming backfires.

### 3.1 Instrument first (no behavior change)

Add a private `_audit()` helper that, given the winning body op list, prints (a) op-count per engine, (b) critical-path length, (c) the RAW-only counterfactual schedule length. This is the harness that already produced §2.1/§2.2; commit it behind an env flag so every subsequent change is measured against the floor, not just the cycle count. (Reuse the standalone script logic below — do not leave it in the shipped `build_kernel` path.)

### 3.2 Redundant-op elimination (the real lever)

Target `_emit_vec_round` (`:321`) and the hash body (`:419-427`). The hash is:
```
val = muladd(val, m4097, K0)                         # :419
node = val^K1 ; addr = val>>19 ; val = node^addr      # :420-421  (stage combine)
val = muladd(val, m33, K2)                            # :422
node = val+K3 ; addr = val<<9 ; val = node^addr        # :423-424
val = muladd(val, m9, K4)                              # :425
node = val^K5 ; addr = val>>16 ; val = node^addr       # :426-427
```
Per (vec,round) this is **3 muladd (vALU) + 6 shift/xor/add (vALU or ALU) + 3 combine (`_combine`)** = 12 vector-op-equiv before the traverse. Concretely investigate:

- **Algebraic fusion of a `t1`/`t2` pair into one op.** Stages 2/4 (`:423-424`, `:426-427`) compute `node = val OP K` and `addr = val SHIFT s` then combine. Where the combine is `^` and one operand is a pure shift of `val`, check whether `multiply_add` or a single masked op can express `(val OP K) ^ (val << s)` in fewer than 3 ops for the *specific* K/s constants in `HASH_STAGES` (`problem.py:439`). The `+`-combine stages were already folded via muladd (see file header `:24-32`); the `^`-combine stages (indices 1,3,5 → shifts 19,9,16) are the 3 that still cost 3 ops each. If any admits a 2-op encoding for its exact constant, that is 32×16 = 512 ops removed = **~7-14 cycles** in the middle.
- **Traverse fusion** (`:432-441`): `rem = val%2`, `i2p1 = 2*idx+1`, `idx = i2p1+rem`. `val%2` is `val&1`; `2*idx+1+rem` could be a single `multiply_add(idx, m2, rem_plus_one)` if `rem+1` is materialized cheaply — but that just moves an op. Instead check: is `idx` for the next round derivable without `%`? `%2` and `&1` are both 1 op; no win. Deprioritize.

For each candidate, the **register/scratch** angle is: fusing may require a *new* dedicated temp (currently `node`/`addr` are recycled 4× per round, `:412-413`). Spending 1-2 of the 65 free words to hold an intermediate that enables a fused op is the intended "trade scratch footprint for op-count" — this is where allocation and op-count meet.

### 3.3 Invariant hoisting

`c["four"]`, `c["two"]`, bit-extract constants are already broadcast once in setup (`:550-574`). Scan `_emit_vec_round` for any *per-vector* value recomputed every round that is round-invariant. The depth is `r % h1` and cycles through 0..10, so most per-round state genuinely changes. The likely-empty result here is *why this is a low-confidence lane* (see §5), but it must be checked because a single hoisted vALU op on the 11 gather/mux rounds is ~30 cycles.

### 3.4 Scratch budget bookkeeping

`alloc_scratch` (`:238`) asserts `<= SCRATCH_SIZE (1536)`. Current use **1471/1536 = 65 free**. Freeing words: the `d3_tree_vec` (`:581`) and `tree_lo` (`:535`) vectors are only read during setup broadcasts; if their lanes are dead after `nb*`/`d3_*` are built, that scratch (16 words) can be reclaimed for hash temps. Verify deadness before reuse (the scheduler's WAR model will catch a live-range bug as a correctness failure, but check by reasoning first).

---

## 4. Day-1 experiment (smallest thing that validates or kills fast)

**Day-1 is already half-done and it is a KILL test, not a build test.** The single most important experiment — the RAW-only counterfactual — is done and returned **negative** (§2.1). Re-run it as the gate for any allocation idea:

```bash
# From /Users/haiyan-mini/Agent4Kernel/vliw
# (1) Baseline + scratch headroom
python -c "from perf_takehome import KernelBuilder; from problem import SCRATCH_SIZE; \
kb=KernelBuilder(); kb.build_kernel(10,2047,256,16); \
print('cycles',len(kb.instrs),'scratch',kb.scratch_ptr,'/',SCRATCH_SIZE,'free',SCRATCH_SIZE-kb.scratch_ptr)"
# expect: cycles 1230 scratch 1471 / 1536 free 65
```

Then the **op-count probe** — pick the single most promising hash-stage fusion from §3.2, implement it, and measure BOTH cycle count and the vALU/ALU op totals:

```bash
python -c "
from collections import defaultdict
from perf_takehome import KernelBuilder
kb=KernelBuilder(); kb.build_kernel(10,2047,256,16)
eng=defaultdict(int)
for b in kb.instrs:
    for e,s in b.items(): eng[e]+=len(s)
print('cycles',len(kb.instrs),'op_by_engine',dict(eng))
"
# Compare op_by_engine against baseline valu=7022 alu=13456 load=2174.
# WIN CONDITION: valu+alu/8 combined-equiv drops AND cycles < 1230 with correctness intact.
```

Full correctness + cycle gate (must pass before claiming any number):
```bash
git diff origin/main -- tests/     # MUST be empty
python tests/submission_tests.py   # MUST print OK and CYCLES: <n>
```

**Kill rule:** if the chosen fusion does not reduce combined vALU+ALU-equiv op-count, abandon it immediately — §2.1 guarantees that only op-count, not scheduling, moves the middle. If *no* hash-stage admits a fewer-op encoding for its exact constants after ~1 day of algebra, the whole lane is dead (see §5) and should be reported as such rather than chasing tail-packing.

---

## 5. Risks & likely failure modes (honest)

1. **The headline risk: the premise is already refuted.** §2.1 shows register renaming to break false deps cannot help (critical path 2, RAW-only is *longer*). If a fresh engineer takes the brief literally and adds dedicated temps, they will spend days and likely *regress* (the greedy scheduler packs worse with more freedom). This doc's entire value is redirecting the effort to op-count.
2. **The hash may be arithmetically irreducible.** OPTIMIZATION_NOTES §3 already reports "缩短 hash 依赖链 / 代数不可约;重排无收益." The `+`-combines are folded; the 3 `^`-combines at shifts 19/9/16 with those exact K constants may have no 2-op form. If so, the op-count floor is fixed and this lane yields **0**. This is the most probable outcome — hence **low confidence**.
3. **Freed scratch doesn't map to a fusion.** Having 65 free words is necessary but not sufficient; if no fusion needs a resident temp, the budget is irrelevant.
4. **Middle is at 99/99/100%** — any op removed from a *non-middle* region (windup/drain) saves nothing (those regions have idle slots). The removed op must land in the saturated middle rounds to count. Depth-0 folding already exploited this asymmetrically; remaining candidates may only touch tail regions.
5. **Packing noise.** OPTIMIZATION_NOTES §5 warns the response surface is noisy at ±3 cycles. A genuine op-count cut should move the floor cleanly; if a change only moves cycles by ≤3 with no op-count change, it is noise, not signal — do not bank it.

---

## 6. Expected payoff + confidence + effort

- **Expected payoff:** If exactly one 3-op→2-op hash-stage fusion is found and lands in the middle: `512 ops / 7.5 ≈ 68` combined-equiv → realistically **1210-1215** after packing. If two independent reductions are found: toward **1190-1195**. Reaching the **1174** floor requires removing ~1 full vector-op-equiv per vec-round across the middle, which is aggressive. Sub-1174 requires a genuine algorithmic op cut (unlikely, see risk 2). Range: **1180 (optimistic) – 1228 (likely, i.e. essentially no win)**.
- **Confidence it beats 1230 at all: LOW.** The specific mechanism in the brief is refuted; the surviving mechanism (op-count via fusion) has already been probed once (notes §3) with no success, so this is a re-attack with sharper measurement, not a fresh idea.
- **Effort:** 2-3 days. Day 1: re-confirm counterfactual + op-count probe on the best fusion candidate. Day 2: exhaustively try the 3 `^`-combine stages + traverse fusion, measuring op-count each time. Day 3: if any candidate reduces middle op-count, tune scratch reuse and re-sweep head/tail; else write the negative result.

---

## 7. Dependencies / prerequisites

- **No external library.** Pure Python; edits confined to `perf_takehome.py` `KernelBuilder`.
- **Scratch budget:** 65 free words confirmed (`1471/1536`); up to ~16 more reclaimable from `tree_lo`/`d3_tree_vec` if proven dead after setup broadcasts (§3.4). Sufficient for holding a handful of fusion intermediates.
- **Measurement harness:** the `op_by_engine` and RAW-only counterfactual snippets in §4 must be kept alongside the cycle test — **cycle count alone is misleading** here because packing noise (±3) can mask or fake a win; the op-count delta is the real signal.
- **Refactor prerequisite:** `_emit_vec_round` currently recycles `node`/`addr` 4× per round (`:412-413`); any fusion needing a live intermediate across a stage boundary requires threading a new named temp through `c[...]` and allocating it in the setup block (`:612-632` per-vector scratch loop). Do this only when a specific fusion demands it.
- **Hard rule:** never touch `tests/` (incl. `frozen_problem.py`); correctness = final `mem[inp_values_p:...]` matches `reference_kernel2` on unseeded random input; only `val` (not `idx`) is checked (`perf_takehome.py:781`).
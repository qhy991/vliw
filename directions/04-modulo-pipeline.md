# Direction: Principled Software Pipelining — Prologue / Steady-State / Epilogue with Compressed-Tail Release

> **Thesis (one line):** Replace the ad-hoc *uniform* diagonal emission in `gen_body` with an explicit prologue / steady-state / epilogue modulo schedule whose **per-block release delays are non-uniform** — front-loaded so both engines fill by ~cycle 8 instead of cycle 20, and back-**compressed** so the last vectors' serial hash-recurrence drains overlap each other instead of decaying `v6→v0` over 21 cycles. This attacks the ~29-cycle windup+drain gap over the 1174 combined-throughput floor.

---

## 0. Empirical grounding (measured today, this shape: fh=10, rounds=16, batch=256, K_VEC=32, n_groups=1)

All numbers below are **measured**, not assumed. `cycles == len(kb.instrs) == 1230` confirmed. Per-engine totals and per-bundle occupancy were extracted by building the kernel once and inspecting `kb.instrs`:

```
Totals:  alu=13456 (floor 1121.3)   valu=7055 (floor 1175.8)   load=2196 (1098)   store=32 (16)   flow=736 (736)
```

**Key correction to the notes:** after the current head/tail `_combine` rebalance, **valu is now the binding single-engine floor at 1175.8**, not alu (1121). The combined alu+valu throughput floor is still ~1174 (6 valu + 12/8 alu = 7.5 vector-op-equivalents ["veq"]/cycle; total work ≈ 8801 veq; 8801/7.5 = 1174).

**Windup (measured):**
- First bundle reaching ~full utilization (alu≥10 AND valu≥5) is **cycle 20**.
- Work done in `[0:20]` = **57 veq**; at the 7.5 veq/cyc steady rate that is only **7.6 cycles** of work spread over 20 cycles → **~12 cycles of windup underfill**.

**Drain (measured) — this is the dominant loss and it is a LATENCY wall:**
- Last bundle with alu≥6 is **cycle 1202**. The region `[1202:1230]` = **28 cycles** contains only **81 veq** → ~10.8 cycles of work → **~17 cycles of pure drain stall**.
- Last bundle with valu==6 (full) is **cycle 1208**; the tail `[1208:1230]` (21 cycles) shows valu monotonically decaying: `…6,4,5,2,3,3,2,2,3,3,1,2,1,2,1,1,2,1,0`. This is the pipeline emptying one vector at a time.
- Critically, from ~cycle 1136 onward **alu is essentially idle (`a0`)** while valu runs 6→0. Example bundles: `1140: a0 v6`, `1198: a8 v1`, `1229: a0 v0`. There is *no independent ALU work left* — the remaining vectors are latency-starved on their serial `val` hash recurrence, so the scheduler can only issue the handful of dependency-ready valu ops. **Engine rebalance cannot fix this; only more overlap or a shorter chain can.**

**Total reclaimable ≈ 12 (windup) + 17 (drain) ≈ 29 cycles** toward 1174, of which the drain portion is latency-bound and only partially reclaimable.

---

## 1. Direction name + thesis

**Name:** Principled software pipelining (explicit prologue/steady-state/epilogue) replacing the uniform diagonal, with a **non-uniform, tail-compressed vector-release schedule**.

**Thesis:** The 56-cycle gap over the 1174 floor is not a scheduler-quality problem (only 17 pure-stall bundles in the middle; middle runs 99%/99%). It is a **pipeline-shape** problem: the current emission releases exactly one block of 4 vectors' round-0 work per diagonal (uniform ramp `delay[b]=b`), which (a) under-supplies the first ~20 cycles and (b) staggers the *finish* times so the epilogue drains vectors one at a time over ~21 cycles. A schedule that ramps up faster and — more importantly — **compresses the finish times of the last blocks** keeps valu at 6 deeper into the tail, collapsing the decay region.

---

## 2. Why this could beat 1230 (quantitative, tied to measured floors)

The gap decomposes into two spatially-distinct regions with different physics:

| Region | Measured cost | Physics | Reclaimable by this direction |
|---|---|---|---|
| **Windup [0:20]** | ~12 cyc underfill | **Supply** — too few ops emitted early; but all 32 vectors' round-0 chains are dependency-independent and *could* start at cycle 0. Pure emission-order/priority artifact. | **~8-12 cyc** (perfect prologue fills by ~cycle 8) |
| **Drain [1202:1230]** | ~17 cyc stall | **Latency** — last vectors' 16-round serial `val` recurrence (~10-deep dep chain/round) has nothing to overlap. valu decays 6→0. | **~5-12 cyc** via tighter tail overlap; more with chain shortening |

- The **windup is fully attributable to emission order**, because cross-vector ops share no scratch addresses (confirmed: the scheduler's dependency edges only ever link same-address reads/writes — see `Scheduler.schedule`, `writers`/`readers` are keyed by scratch `addr`, lines 82-116). So every vector's round-0 op is dependency-ready from cycle 0. The *only* reason the windup underfills is that (i) `gen_body` emits block `b`'s work `b` diagonals late, and (ii) the greedy scheduler's priority tiebreaker is the **op emission index** `i` in `lambda i: (-hgt[i], -succ[i], i)` (line 197) — so late-emitted ops lose ties and pack late. Emitting all blocks' round-0 work earlier directly raises early supply.
- The **drain is a genuine latency wall** but the *shape* of the wall is controlled by release timing. Currently blocks finish staggered (block b finishes ~1 diag after block b-1), so vectors retire one-by-one → the long decay. If the last ~2 blocks are released so they **finish within the same few cycles**, their independent valu work coexists, holding valu near 6 until a single ~10-cycle unhidable chain remains at the very end.

**Theoretical target:** a perfectly pipelined schedule leaves only one unhidable single-vector final-round serial chain (~8-10 cycles) plus store drain (32 stores / 2 = 16, but overlappable with valu). So the floor for this approach is ≈ **1174 + ~10 ≈ 1184**. Realistic first-cut: reclaim windup fully (~10) and half the drain (~8) → **~1210-1218**; aggressive with tail compression + rebalance → **~1188-1200**.

---

## 3. Mechanism: exactly what changes in `perf_takehome.py`

All changes are confined to **`KernelBuilder.gen_body`** (lines 679-716), its call site (the rotation loop lines 718-726), and the `_combine` phase policy (lines 301-313, 230-233). No ISA changes; no `tests/` changes.

### 3.1 Parameterize the release schedule (core change)

Current code (lines 686-693) hard-codes a uniform ramp via `step=4`:
```python
perm = [(j - rot) % K for j in range(K)]
ppos = {perm[p]: p for p in range(K)}
n_diag = (K + step - 1) // step + rounds - 1
for diag in range(n_diag):
    for q in range(K):
        j = perm[q]
        r = diag - ppos[j] // step          # <-- block start delay = ppos[j]//step, i.e. b
        if 0 <= r < rounds: ... emit round r of vector j ...
```
Here `ppos[j]//step` is the block index `b∈{0..7}`, and vector j runs round `r` at diagonal `b + r`. **The start delay of block b is exactly `b`** — a uniform ramp of slope 1 block/diagonal.

**Replace `ppos[j]//step` with an explicit per-block delay array `start_delay[b]`:**
```python
# start_delay[b] = diagonal at which block b begins round 0.
# Uniform baseline reproduces current behavior: start_delay = [0,1,2,3,4,5,6,7].
# Front-loaded prologue + compressed epilogue, e.g.:
#   start_delay = [0,0,1,1,2,2,3,3]   (ramp up 2 blocks per diag, then trail)
# The delay of the LAST few blocks is reduced relative to uniform so their
# round-15 finish diagonals coincide -> tail compression.
def block_of(pos):  # pos in permutation -> block index
    return pos // step
for diag in range(n_diag):
    for q in range(K):
        j = perm[q]; b = block_of(ppos[j])
        r = diag - start_delay[b]
        if 0 <= r < rounds: ...emit...
```
`n_diag = max(start_delay) + rounds`. This is a *superset* of the current schedule (uniform `start_delay=range(8)` reproduces 1230 exactly — a required regression check).

### 3.2 Make block size / count a searchable knob

`step` is fixed at 4 (line 683) → 8 blocks of 4. Expose `step ∈ {2,4,8}` and even **per-block sizes** (blocks needn't be equal). Smaller blocks near the tail (e.g. last two blocks of size 2) give finer control over finish-time compression. Structure: replace the flat `ppos[j]//step` with a precomputed `pos_to_block[pos]` list so block boundaries are arbitrary.

### 3.3 Phase-aware `_combine` policy (generalize the head/tail counter)

Today `_combine` (lines 301-313) uses a *global emission counter* `_combine_no` against `_combine_head=10 / _combine_tail=100`. Replace the scalar counter with a **per-(vector, round) phase tag**: when emitting a vector-round, pass whether it is in the prologue diagonals (`diag < prologue_end`) or epilogue diagonals (`diag >= n_diag - epilogue_start`). In those phases emit combines on the idle engine:
- **Prologue:** alu AND valu both underfilled — put combines on **valu** only if valu is the scarcer of the two given current supply; else alu. (Measured windup is 85%/79%, so slight valu bias.)
- **Epilogue:** **alu is idle (a0), valu is the bottleneck.** So in the epilogue, do the OPPOSITE of the middle — emit combines on **alu (`v_alu_scalar`)** to *drain the valu recurrence pressure onto the idle ALU*. This is the single highest-value micro-change the profile implies: bundles `1140-1200` are `a0 v6` — every combine there could be an 8-slot alu op instead, freeing valu slots for the *serial* muladds that actually gate the drain.

Wire this by threading `diag`, `prologue_end`, `epilogue_start` into `_emit_vec_round` (it already takes `j`; add a `phase` kwarg) and into `_combine`.

### 3.4 Store scheduling in the epilogue

vstores are emitted per-vector right after the last round (lines 709-714, store engine, 2/cycle). With tail compression the 32 stores could clump. Keep them spread; if they bottleneck (store floor is only 16), consider emitting the final-round `val` of tail vectors slightly earlier so stores interleave. Low priority (store floor 16 << drain length).

### 3.5 Search harness

The rotation loop (lines 718-723) currently tries `K=32` rotations and keeps the min. Extend it to also sweep the schedule shape:
```python
best_body = None
for schedule in candidate_schedules():        # (step_layout, start_delay, prologue_end, epilogue_start)
    for rot in range(K):                       # keep existing rotation search
        rnd = gen_body(rot, schedule)
        bundles = Scheduler().schedule(prefix + rnd)
        if best_body is None or len(bundles) < len(best_body):
            best_body = bundles
```
`candidate_schedules()` should be a small curated set first (see Day-1), not a blind grid — each `Scheduler().schedule` pass on ~14k ops costs ~2-4 s, and 32 rotations already make one build take ~1-2 min.

---

## 4. Day-1 experiment (smallest thing to validate/kill fast)

**Goal:** in one afternoon, prove that (a) the schedule is truly parameterizable without breaking correctness, and (b) the epilogue-combines-to-ALU idea moves cycles. Two cheap, decisive probes:

### Probe A — refactor to `start_delay` and confirm the identity (30 min)
Refactor `gen_body` per §3.1 with `start_delay = list(range(8))` and `step=4`. Rebuild and confirm **exactly 1230** (bit-identical schedule). This de-risks the refactor before any tuning.

Measure with:
```bash
cd /Users/haiyan-mini/Agent4Kernel/vliw
python -c "from perf_takehome import KernelBuilder; kb=KernelBuilder(); kb.build_kernel(10,2047,256,16); print('CYCLES:', len(kb.instrs))"
```
(`n_nodes = 2**(10+1)-1 = 2047`. cycles == len(instrs) for n_groups=1, so no simulator run needed for cycle count.)

### Probe B — epilogue combines onto idle ALU (1-2 hr)

> **REVIEW CAVEAT:** this probe's premise conflicts with the already-swept evidence. The
> existing `head=10/tail=100` optimum came from a 64+25-build grid (OPTIMIZATION_NOTES
> §4.1) in which `tail=0` — i.e. tail combines staying on ALU, exactly what this probe
> proposes — was in the grid and **lost** to tail-on-valu. The "a0 v6" drain snapshot is
> the profile *of the tuned optimum*, not evidence that the un-tuned alternative is
> better; the drain being valu-full with combines on valu does not imply combines on ALU
> drains faster (the sweep says it doesn't). Run the probe only as a cheap sanity check;
> expect it to regress, and do not burn more than the stated 1-2 hours.

Independently of the release schedule, change `_combine` so that combines emitted in the **last ~150 emission-order instances go on ALU** (they currently go on valu via the `_combine_tail=100` valu branch — flip the tail branch to `v_alu_scalar`). This directly tests the `a0 v6` observation: the drain has 12 idle ALU slots/cycle and valu is the bottleneck, so moving tail combines *off* valu should shorten the drain. Sweep `_combine_tail ∈ {60,100,150,200}` with the branch flipped:
```bash
for T in 60 100 150 200; do
  python -c "
from perf_takehome import KernelBuilder, KernelBuilder as KB
import perf_takehome as P
# monkeypatch the tail count for a quick sweep
kb=KernelBuilder(); kb._combine_tail=$T; kb.build_kernel(10,2047,256,16); print('tail=$T CYCLES:', len(kb.instrs))"
done
```
(For a clean sweep, add a constructor/param hook rather than monkeypatch; the above shows intent.)

**Kill criterion:** if flipping the tail combines to ALU and sweeping the delay of the last two blocks yields **no configuration < 1225** after Probe A+B, the latency wall is harder than modeled and this lane should pivot to §3.3's chain-shortening (or defer to the reassociation lane). **Go criterion:** any config ≤ 1220 confirms the tail is reshapeable; proceed to the full non-uniform `start_delay` search.

### Final correctness gate (run before claiming any win)
```bash
cd /Users/haiyan-mini/Agent4Kernel/vliw
git diff origin/main -- tests/          # MUST be empty
python tests/submission_tests.py        # MUST print OK; validates val[] on 8 UNSEEDED random inputs
```

---

## 5. Risks & likely failure modes (honest)

1. **The drain is a hard latency wall (highest risk).** The measured `a0 v6→v0` decay is a single-vector serial hash chain with nothing to overlap. Tail *compression* helps only until the very last vector, whose ~10-cycle final-round chain is fundamentally unhidable. If compression just moves the decay earlier without shortening total work, gains cap at ~5-8 cycles. **Mitigation:** combine with §3.3 (epilogue combines→ALU) which is orthogonal and attacks the valu bottleneck directly.
2. **Greedy scheduler fights the schedule.** The scheduler's priority is height-then-successor with emission-index tiebreak (line 197). A hand-designed release order can be *overridden* by the greedy pass if height/succ metrics dominate. The lever we actually control is emission order (the tiebreak) and *which ops exist when*. If height dominates, non-uniform delays may not translate to the intended bundle placement. **Mitigation:** verify empirically after each schedule change (cheap: just count bundles); if the scheduler ignores the shape, we may need to also touch the priority `KEYS` (but that risks regressing the well-tuned middle — do NOT change the global key; at most add a phase-scoped nudge).
3. **Windup gains are small (~12 cyc cap) and may be packing-noise.** The notes already warn the tail response surface is noisy (1230-1240 jitter). Some of the 12 windup cycles may be irreducible setup/broadcast dependencies (the 15 broadcast_const + 2 vload ops in setup, lines 486-608, must complete before body round-0 can read constants). **Mitigation:** measure the setup tail explicitly; the first body op cannot precede its constant's broadcast.
4. **Search cost.** Each build = 32 rotations × ~2-4 s scheduler = 1-2 min. A naive grid over `start_delay` (8 blocks × several delays each) explodes. **Mitigation:** curate candidate schedules from the model (front-load 2/diag, compress last 2 blocks); drop the rotation sweep to `range(0, K, 4)` during exploration, restore full sweep only for the final measurement.
5. **Regression in the middle.** Any schedule change that de-staggers depths risks all-gather or all-no-load cycles (load floor 1098 / valu idle). The uniform diagonal was chosen precisely to keep depths mixed. **Mitigation:** the `start_delay` must preserve depth-mixing in steady state — only the *ends* should deviate from uniform. Keep steady-state blocks at uniform slope; bend only prologue/epilogue delays.

---

## 6. Expected payoff & effort

- **Cycle estimate:** optimistic **1188** (windup fully reclaimed ~10 + drain half-reclaimed ~15 + epilogue-ALU combines ~7), pessimistic/likely **1218** (windup ~8 + modest drain ~4). Best single cheap win is likely Probe B (epilogue combines → ALU): plausibly 5-15 cycles alone.
- **Confidence it beats 1230 at all:** **medium.** Probe B has a strong mechanistic basis (12 idle ALU slots/cycle for ~90 drain bundles while valu is the bottleneck) — that alone should yield something. Reaching <1200 is lower confidence because of the latency wall (risk 1).
- **Effort:** Day 1 = refactor + two probes (identity check + tail-ALU sweep). Days 2-3 = non-uniform `start_delay` + per-block-size search + phase-aware combine. Days 4-5 = combine with chain-shortening if the wall dominates, plus full correctness/regression sweep. **~3-5 days** for a serious attempt; a first ≤1220 result is achievable Day 1-2.

---

## 7. Dependencies / prerequisites

- **No external libraries.** Pure Python edits to `perf_takehome.py`.
- **No new scratch budget** for the base plan (release-schedule change reuses existing per-vector scratch). If §3.3 needs to distinguish phases per vector, it's a compile-time tag, not runtime scratch.
- **Refactor prerequisite:** §3.1 (parameterize `start_delay`) must land and reproduce 1230 bit-identically before any tuning — this is the safety net.
- **Measurement harness:** a small driver that builds and prints `len(kb.instrs)` for a candidate schedule (cycle count needs no simulator for n_groups=1). Add a per-bundle occupancy dumper (already prototyped: build once, iterate `kb.instrs`, count `len(b.get(engine,[]))`) to watch the windup/drain shape after each change — this is the primary feedback loop, far faster than the full `submission_tests.py`.
- **Correctness gate:** `python tests/submission_tests.py` (unseeded, validates `val[]` only) before any claimed win; `git diff origin/main -- tests/` must be empty (hard rule).
- **Coordination note:** §3.3's epilogue-combine-to-ALU and any chain-shortening overlap conceptually with the reassociation lane — if that lane exists, share the finding that reassociation pays off in the *latency-bound drain* (not the throughput-bound middle, where the notes correctly found it dead).

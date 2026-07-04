# 11 Long-Range Optimization Directions — Index & Ranking

Baseline: **1230 cycles** (throughput floor 1174). Each direction has its own worktree
under `explore/<key>/` on branch `explore/<key>`, seeded with `DIRECTION.md`.

> **SECOND-PASS REVIEW (validated in the simulator/reference traces — see §"Second-pass
> corrections" below):** #2's headline was over-counted (net −224 valu ops, not −512;
> corrected floor ~1135, not ~1097 — still the biggest lever, ~40 cycles smaller). #3's
> core identity was **wrong as written** and its Day-1 script would have falsely killed
> the direction (fixed: invariant is `idx == 2^d−1+p`; mechanism rewritten to re-permuted
> parity-indexed tables). A **new direction #11** was found, implemented on a scratch
> copy, and measured: round-10's entire idx update plus the initial idx vloads are dead
> code (−128 valu, −32 flow, −63 load, correctness OK on 3 seeds) — land it first.

## Summary table (post-review)

| # | Direction | Attack surface | Est (low–high) | Conf |
|---|---|---|---|---|
| 11-dead-code-idx **(NEW)** | Dead-idx elimination: round-10 traverse+wrap and idx vloads are dead code | valu/flow/load op-count (floor drop **measured**: −17 combined) | **1228 measured** (coarse re-sweep); 1220–1228 | proven |
| 02-hash-opcount | Defer stage-5 K5 into node broadcasts (**corrected: 7 rounds, −224 valu**) | valu-op-count (binding floor 1176→1138.5) | 1180–1220 | medium-high |
| 03-round-structure | Parity-carry traversal (**corrected: re-permuted tables keyed on raw parities**) | valu-op-count (binding floor) | 1170–1225 | medium |
| 10-autotuner | Global Multi-Knob Autotuner (SA + coordinate-descent over the combine mask) | windup-drain + scheduler-suboptimality | 1195–1226 | medium |
| 09-data-layout | Depth-Interleaved SIMD Layout: fill windup/drain by mixing depths | scheduler-suboptimality / windup-drain | 1180–1225 | low |
| 01-exact-scheduler | CP-SAT modulo-resource scheduling over the drain tail | scheduler-suboptimality + windup-drain | 1180–1225 | low |
| 04-modulo-pipeline | Prologue/Steady-State/Epilogue pipelining (Probe B caveat added) | windup-drain (latency-wall component) | 1188–1218 | medium |
| 06-regalloc-hazards | Scratch-as-op-count (valuable as refutation of rename-to-parallelize) | alu/valu op-count | 1180–1228 | low |
| 08-flow-vselect | Flow relief on depth-3 muxes (§3.3 wrap part superseded by #11) | flow-engine / windup-drain | 1205–1228 | low |
| 05-cross-vector-share | Cross-vector redundancy at shallow depths | flow-engine (non-binding) | 1195–1232 | low |
| 07-load-engine-lut | LUT-offload to LOAD engine (self-refuted; kept as documentation) | load-engine (non-binding) | 1215–1230 | low |

## Reviewer critique & ranking

I'll review each direction critically, then rank them. Let me note upfront that these are proposals about a VLIW kernel's scheduling and op-count floors — the claims are internally quantified, so my critique focuses on internal consistency, distinctness, and risk rather than re-deriving the machine model.

Here is my review.

---

**1. [01-exact-scheduler] CP-SAT modulo scheduler**
The thesis is honest about where the gap lives (the ~56-cycle drain tail, not the middle band), which is the right target. But it overlaps heavily with #4, #9, and #10 — all four attack "windup/drain scheduler-suboptimality." The distinction is only in *mechanism* (CP-SAT solver vs. hand-crafted modulo schedule vs. data re-phasing vs. SA autotuner), not in the floor being attacked. The estimate (1180-1225) is honest and its own low confidence flags the core risk: CP-SAT on a modulo-resource problem with engine-assignment as a decision variable is a hard combinatorial model that may not solve to optimality (or even feasibility) within a usable window, and the payoff ceiling is only ~56 cycles even if it *does* solve. **Biggest risk: solver intractability/tuning cost for a capped payoff that a cheaper heuristic (#10) might capture most of.**

**2. [02-hash-opcount] Defer stage-5 K5 into node broadcast**
This is the standout: it is the only direction that lowers the *binding throughput floor itself* (valu 1176→1090, combined 1174→~1090) rather than fighting for tail slack under a fixed floor. Genuinely distinct from all nine others — every other proposal is capped at ~1174, this one moves the cap. The algebra is the whole risk: deferring `t1 = a^K5` by carrying `valx = trueval^K5` and baking K5 into node constants is a clean XOR-associativity move *if and only if* K5 truly sits at the round boundary with no intervening nonlinear op (shift/mul/mod) that doesn't commute with XOR. The claim "512 valu ops deleted" is specific and checkable. **Biggest risk: an intervening nonlinear stage breaks the associativity and the whole 86-cycle gain evaporates — but this is binary and cheap to verify on paper first.**

**3. [03-round-structure] Parity-carry, delete idx reconstruction**
Also attacks the binding valu floor (distinct in mechanism from #2 — removing i2p1 muladds + &-extracts vs. deferring an XOR), so #2 and #3 are complementary, not overlapping, and could in principle stack. The reasoning that "node-select conditions at shallow depths ARE the accumulated parity bits val%2 already produces" is plausible but the estimate range is wide and soft (200-384 valu ops, 1150-1225) which signals the author isn't sure how many rounds actually admit the parity-threading. **Biggest risk: the parity-bit identity holds only if idx reconstruction is genuinely redundant with already-computed parity — if the idx muladd folds in a per-node constant or the traversal isn't a clean binary tree, you can't thread parity and you've deleted nothing.** The nonlinearity caveat is handled honestly, but this needs the identity proven before any coding.

**4. [04-modulo-pipeline] Prologue/steady-state/epilogue with compressed tail**
Directly overlaps #1, #9, and #10 — same windup/drain target, and "explicit modulo schedule with non-uniform release delays" is essentially the hand-built version of what #1's CP-SAT would find and what #10's autotuner would search. Not distinct enough to fund alongside those. The estimate (1188-1218) is more conservative than #1's, which is appropriately humble for a hand-crafted schedule. It also quietly admits a "latency-wall component in the epilogue" — meaning part of the drain is a hard recurrence latency that *no* repacking can reclaim, which caps the realistic gain below the stated range. **Biggest risk: the epilogue is latency-bound not throughput-bound, so tail compression hits a wall well short of 1174 and the human effort of hand-authoring a modulo schedule is wasted relative to letting #10 search it.**

**5. [05-cross-vector-share] Collapse shallow-depth vselect tournaments**
Overlaps #8 substantially — both target the 736 flow floor via the shallow-depth vselects, #5 by collapsing depth-2/3 tournaments and #8 by re-engining depth-3 vselects to arithmetic. The framing here is muddled: it claims to attack "the flow-engine mux floor, not the hash" but then the payoff is described as "freeing windup/drain slack," which is a different floor — and since flow at 736 is *not* the binding floor (valu ~1176 and combined 1174 are), relieving flow only helps if flow is a *local* co-limiter in the tails, which is exactly #8's narrower and more honest claim. The estimate (1195-1232) tops out *above* the current 1230, i.e., it might do nothing. **Biggest risk: flow is not the global binding constraint, so collapsing muxes buys nothing in the middle and only marginal tail slack — the direction confuses a non-binding floor for a bottleneck.**

**6. [06-regalloc-hazards] Scratch-as-op-count**
Valuable mainly as a *refutation*: it correctly and explicitly kills the naive "register-rename to break serialization" idea (critical path = 2, false-dep headroom = -19, renaming makes it worse). That negative result is worth having. But as a *positive* direction it's vague — "spend 65 free scratch words to keep values resident / hoist invariants / fuse recompute" is not a specific op-count reduction, it's a hope that one exists. It partially overlaps #2/#3 (any op it fuses is likely an op those already target) without naming which ops. **Biggest risk: the positive claim is unspecified — there may simply be no invariant-hoisting or recompute-fusion opportunity left once #2/#3 are done, making the 65 scratch words a solution in search of a problem.**

**7. [07-load-engine-lut] LUT-offload (self-refuted)**
The author has already refuted the headline (no gather instruction; load engine 100% saturated in the middle [300-1050]; only the cheap `<<` low-half is LUT-able). Intellectually honest and the refutation is well-argued. The salvage — "gather-reduction on the depth≥4 node fetch to attack the 1098 load floor" — is the only live sub-claim, but the estimate (1215-1230) essentially says "at best a few cycles, likely nothing," and the load floor at 1098 is below the binding 1174 anyway, so even a win here doesn't move the binding constraint unless load becomes co-binding in a tail window. **Biggest risk: the salvaged gather-reduction attacks a non-binding floor (1098 < 1174), so it cannot move total cycles unless load is a local tail limiter — and the author hasn't shown it is.**

**8. [08-flow-vselect] Shrink/re-engine vselect muxes**
The more honest and narrowly-scoped twin of #5. It correctly concedes flow (736/736) is *not* the middle-band bottleneck and claims only local relief in the head [100-175] and drain [1130-1180] windows by moving depth-3 vselects onto engines idle in those tails. That's a legitimate windup/drain play with a real mechanism. But it overlaps #5's target, and its payoff is bounded by how flow-limited those specific windows actually are. **Biggest risk: converting vselects to arithmetic selects pushes load onto valu/alu, which are the *global* binding floor — so you may relieve a local flow limiter only to raise the binding valu floor, a net loss unless the tail engines are genuinely idle there.**

**9. [09-data-layout] Depth-interleaved SIMD layout**
The most *architecturally interesting* of the windup/drain cluster and arguably the most distinct within it: instead of repacking a fixed schedule (#1/#4/#10), it changes the element-to-vector phase assignment so concurrent vectors span complementary depths, letting a gather-heavy round's idle ALU absorb a no-gather round's surplus. This is a real, different lever (data layout, not scheduling). Overlaps the *target* (windup/drain gap) with #1/#4/#10 but not the *mechanism*. **Biggest risk: de-phasing the batch so vectors sit at different depths may break the lockstep assumptions the rest of the kernel and the gather/broadcast constants rely on, turning a scheduling win into a correctness/complexity mess — and the gain is still capped at the ~56-70 cycle tail.**

**10. [10-autotuner] Global multi-knob autotuner (SA + coordinate descent)**
This is the pragmatic capture-play for the entire windup/drain cluster: it subsumes the *tuning* portion of #1, #4, and the engine-assignment knob generally, searching the full per-(round,vector) 0/1 mask that the greedy scheduler responds to nonlinearly, driven by an exact bundle-count oracle. That subsumption is also its overlap problem — funding #10 makes #1 and #4 largely redundant (and vice versa). The estimate (1195-1226) is appropriately modest and its medium confidence is justified by having a real oracle to optimize against. **Biggest risk: SA/coordinate-descent over a large discrete mask on a nonlinear response surface can stall in local minima and burn compute for a single-digit-cycle gain — but with a fast exact oracle and 10-core parallelism, the downside is bounded and it's the cheapest way to test whether the tail gap is *reachable at all*.**

---

### Ranking, best-to-worst by expected value (payoff × probability) — REVISED AFTER SECOND-PASS REVIEW

0. **#11 [11-dead-code-idx] (NEW) — land FIRST; already beats 1230.** The only direction
   that is implemented and measured: deletions land exactly as predicted (−128 valu,
   −32 flow, −63 load), correctness verified on 3 seeds. Naive drop-in measured 1234
   (stale head/tail knobs eat the floor drop), but the first coarse 10-config re-sweep
   found **(head=20, tail=120) → 1228**, with 1229/1230 neighbors corroborating. Effort
   remaining is a finer grid + the standard correctness gate. The lowered floors are the
   base every other direction should stack on.

1. **#2 [02-hash-opcount]** — Still the biggest single lever, but **corrected**: net
   deletion is 224 valu ops (7 deferral rounds), not 512; floor drop is ~37 valu-floor
   cycles / ~30 combined, not ~85. The gather path is provably net-zero — the selective
   7-round variant is the final form, which also removes the output-fixup seam. The Day-1
   guard in the original draft (`depth < 4`) was on the wrong variable and would have
   produced a silently wrong kernel on rounds 3/14 — fixed to next-round depth.

2. **#3 [03-round-structure]** — Still second among floor-movers, but the original doc's
   core identity was **false** (idx low bits are borrow-mixed parities, not parities;
   verified 1536/1536 counterexamples) and its Day-1 script would have false-killed the
   lane. Corrected mechanism: re-permute the broadcast tables to be indexed by raw parity
   vectors via the verified invariant `idx == 2^d − 1 + p` (0/4096 violations). The
   maintenance op disappears entirely (compile-time ring renaming), but scratch pressure
   is now the primary risk (768 words naive vs 65 free).

3. **#10 [10-autotuner]** — Unchanged assessment: best of the windup/drain cluster,
   subsumes the tuning of #1/#4, exact oracle, bounded downside. **Note:** #11's re-tune
   step is a miniature of this lane; if #11's manual sweep stalls, hand it to #10.

4. **#9 [09-data-layout]** — Unchanged: most distinct mechanism in the tail cluster.

5. **#1 [01-exact-scheduler]** — Unchanged: fund only if #10 proves the gap reachable but
   can't close it.

6. **#4 [04-modulo-pipeline]** — Unchanged rank; a review caveat was added to Probe B
   (its premise contradicts the already-swept tail=0 grid point — expect it to regress).

7. **#6 [06-regalloc-hazards]** — Unchanged: keep the refutation, deprioritize the
   positive claim.

8. **#8 [08-flow-vselect]** — §3.3 (wrap-as-multiply) superseded by #11 (the wrap is
   dead code, deletion beats substitution). Remaining scope is depth-3-only; rank
   unchanged.

9. **#5 [05-cross-vector-share]** — Unchanged: cut in favor of #8.

10. **#7 [07-load-engine-lut]** — Unchanged: bottom, kept as documentation.

**Bottom line (revised):** The floor-movers are now three, and they stack: **#11 (−17
combined, proven, hours) → #2 (−30 combined, medium-high, 1-2 days) → #3 (−up to 64,
medium, scratch-gated)**. Together they put the combined floor near ~1090-1118, which is
worth more than everything the nine tail-fighters can collectively reach under the old
1174 cap. Fund the tail cluster with exactly one capture-play (**#10**) run *after* the
floor-movers land, since every mask/knob optimum shifts when the op profile changes.

### Second-pass corrections (what changed and why)

- **#2:** deferral validity depends on the *successor* round's node source; gather
  successors cost +1 op each, cancelling those rounds. Net −224, floor 1176→1138.5
  (verified by op-count arithmetic against the measured 7055-valu build). Day-1 recipe's
  `if depth < 4` guard replaced with `(r+1) % h1 < 4` — the original produced a wrong
  kernel on rounds 3/14.
- **#3:** `idx&1 == pbits&1` fails on every shallow-round sample (complement at d1,
  borrow-mixed at d2/d3). Verified invariant `idx == 2^d − 1 + p` substituted; mechanism
  rewritten to parity-indexed re-permuted tables; Day-1 script replaced with one that
  passes (already run: 0/4096).
- **#4:** Probe B caveat (contradicts the swept grid; the "a0 v6" profile is of the tuned
  optimum, not evidence against it).
- **#8:** §3.3 superseded by #11.
- **#11 (new):** round-10 idx update + initial idx vloads are dead code; wrap at depth 10
  is additionally unconditional (256/256 wrap to 0). Implemented and measured on a scratch
  copy: op deltas exact, correctness OK ×3 seeds, floors −17 combined; realized cycles
  pending the head/tail re-sweep.
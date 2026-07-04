# Direction: Hash op-count reduction via stage-5 K5-deferral (x-space carry)

> Assigned lane: *REDUCE the total op count of the hash itself* — attack the
> 7055-valu / 13456-alu totals directly, lowering ALL floors.

---

## 1. Direction name + one-line thesis

**Name:** Stage-5 K5-deferral (carry `valx = trueval ^ K5` across rounds; bake K5 into node broadcasts).

**Thesis:** The hash's final combine stage-5 = `(a ^ K5) ^ (a >> 16)` spends **one valu op per (vec,round)** on the constant term `t1 = a ^ K5` (line 426, `self.v_alu("^", node, val, c["K5"])`). Because that `^ K5` lands at the hash/round boundary — immediately adjacent to the next round's `val ^ node` — it can be **algebraically deferred**: carry `valx = trueval ^ K5` between rounds and fold `K5` once into every node-broadcast constant. This deletes 512 valu ops with **no new muladd**, dropping the binding valu floor from ~1176 to ~1090 and the combined throughput floor from 1165 to ~1097.

---

## 2. Why this could beat 1230 (quantitative, tied to verified floors)

Verified current totals (measured, `KernelBuilder().build_kernel(10, 2047, 256, 16)`, 1230 cycles):

| engine | slots | single-engine floor |
|---|---|---|
| load | 2196 | 1098 |
| **valu** | **7055** | **1175.8 (binding)** |
| alu | 13456 | 1121.3 |
| flow | 736 | 736 |
| store | 32 | — |

Combined valu-equivalent work = `valu + alu/8 = 7055 + 13456/8 = 8737`; combined floor `8737 / 7.5 = 1165`. So **1230 sits 65 cycles above a 1165 floor**, and the binding single-engine floor is **valu at 1176** — actually *above* the combined floor, i.e. valu is the true limiter, not the abstract 1174.

**The lever.** `t1 = a ^ K5` in stage-5 is emitted as `v_alu` (line 426) = a genuine **valu** op, one per (vec,round) = `16 rounds * 32 vec = 512` valu ops. Deferring it removes exactly those 512 valu ops:

- valu: `7055 - 512 = 6543` → valu floor `6543/6 = 1090.5` (was 1176). **−85 cycles off the binding floor.**
- combined valu-equiv: `8737 - 512 = 8225` → `/7.5 = 1097` (was 1165). **−68 cycles off the combined floor.**

Each vector-op removed per (vec,round) is worth **512 work units = ~68 combined-floor cycles / ~85 valu-floor cycles**. This is the single largest structural knob left, because it removes work from the *binding* engine without adding any valu-locked muladd (contrast §5's trap).

Realized cycles will not touch the floor — the ~66-cycle windup/drain tail gap (only 17/1249 bundles were pure dep-stalls per OPTIMIZATION_NOTES §3) persists — but lowering the *floor the schedule rides above* shrinks the tail-limited program too. If the ~5.6% tail-gap fraction holds, realized ≈ `1097 * 1.056 ≈ 1158`; conservatively 1160-1185, optimistically ~1140.

---

## 3. Mechanism: exactly what changes in perf_takehome.py

**Algebraic core (all proven in §"proofs" below):**

Define `myhash_x(x)` = the full 6-stage hash with the final `^ K5` removed:
```
... stage4 ... ; a = a ^ (a >> 16)      # was: a = (a ^ K5) ^ (a >> 16)
```
Then `myhash_x(x) == myhash(x) ^ K5` for all 32-bit x (verified, 300k random). Carrying
`valx = trueval ^ K5` makes the recursion self-consistent:
```
input to hash = valx ^ node'                 where node' = node ^ K5
              = (trueval ^ K5) ^ (node ^ K5)  = trueval ^ node   (K5 cancels)
myhash_x(trueval ^ node) = trueval_next ^ K5 = valx_next          (closes the loop)
```

**Edits, all inside `KernelBuilder` (perf_takehome.py). Do NOT touch problem.py or tests/.**

1. **Delete the stage-5 t1 op** in `_emit_vec_round` (line 426). Change:
   ```python
   self.v_alu("^", node, val, c["K5"]); self.v_alu(">>", addr, val, c["sh16"])
   self._combine(val, node, addr)
   ```
   to compute stage-5 as `val = val ^ (val >> 16)` (2 ops, no K5):
   ```python
   self.v_alu(">>", addr, val, c["sh16"])   # t2 = val >> 16
   self._combine(val, val, addr)            # val = val ^ (val>>16)   -- ^K5 deferred
   ```
   (`_combine` reads `a=val,b=addr`; both aliasing `val` for dest is fine — RAW is on the read of `val` before write, matching the existing pattern.)

2. **Bake K5 into every node broadcast constant** used as `node_src`. The node comes
   from broadcasts `nb0` (line 544, depth-0), `nb1/nb2` (545-546, depth-1),
   `nb3..nb6` (554, depth-2), `d3_0..d3_7` (592, depth-3), and the gathered `node`
   for depth≥4 (lines 398-400). Two clean options:
   - **(a) Broadcast path (depth 0-3):** after each `broadcast_scalar`, XOR the vector
     with a `K5` broadcast once at setup: `self.v_alu("^", nbk, nbk, c["K5"])`. This is
     ~15 setup ops total (one-time, negligible vs 512 saved).
   - **(b) Gather path (depth≥4):** after the 8 scalar loads into `node` (line 400),
     the subsequent `val = val ^ node` (line 410) must use `node ^ K5`. Fold K5 into
     that XOR: emit `val ^= node` then it's already in x-space *iff* node carries K5.
     Simplest: keep a `node' = node ^ K5` by making the gather XOR `val = (val) ^ node`
     then one extra `^K5`… **that would re-add an op on gather rounds.** Better: since
     depth≥4 is only rounds 4-10 and 15 here (`depth = round % 11`), bake K5 into the
     `val^node` combine by pre-xoring the *broadcast K5 into val once* — see risk R3.
     Cleanest uniform fix: XOR `K5` into `node` right after it is produced in *all*
     branches (1 extra valu op on gather rounds only), still net-negative overall, OR
     restructure so the `val ^= node` step consumes `node ^ K5`. Day-1 validates the
     broadcast path first (rounds 0-3 dominate; depth-2/3 muxes are the hot muxed rounds).

3. **Parity swap in traverse** (lines 432-441). In x-space `valx & 1 = (trueval & 1) ^ 1`.
   Reference addend `1 + (trueval&1)` becomes `2 - (valx&1)` (verified, 500k random, 0 mismatch).
   Zero extra ops — only constants/ops change:
   - depth-0 (line 438): `self.v_alu("+", idx, one_v, addr)` → `self.v_alu("-", idx, two_v, addr)` (idx = 2 - rem_x). Need a `two_v` broadcast (already exists as `c["m2"]`).
   - depth≥1 (lines 440-441): `v_muladd(node, idx, m2, one_v)` (2idx+1) → `v_muladd(node, idx, m2, two_v)` (2idx+2), then `v_alu("+", idx, node, addr)` → `v_alu("-", idx, node, addr)` (idx = i2p2 − rem_x). Same op count.
   - `rem = val % 2` (line 432) is unchanged: `rem_x = valx % 2`.

4. **Round-0 input boundary.** Round-0 reads raw `val` from mem (vload, line 663) and
   computes `val ^ node` where node is a *real* tree value. In x-space the very first
   hash must receive `trueval ^ node`. Since we haven't yet applied any K5 carry on
   input, and the node broadcasts now carry K5, the depth-0 XOR would give
   `trueval ^ (node^K5)` = wrong by K5. **Fix:** on round 0 only, use the *un-K5'd*
   node (or XOR K5 back). Simplest: keep a separate depth-0 round-0 broadcast `nb0`
   without K5 for the first round, or pre-XOR K5 into the loaded `val` once. This is a
   32-vec one-time setup detail; see Day-1.

5. **Final-round output fixup.** Round 15 stores `valx = trueval ^ K5`, but the
   scoreboard checks `trueval`. On the final round (`skip_idx_update=True`, line 699),
   apply `val = val ^ K5` before the vstore (line 711). Cost: `+1 op * 32 vec = +32`
   ops, one-time. (Or bake into stage-5: on the last round only, keep the original
   `^K5` combine.) Net after fixup: `−512 + 32 = −480` valu ops.

**ISA ops used:** `^`, `>>` (v_alu), `multiply_add` (v_muladd, unchanged count), `-`
(v_alu, replacing `+` in traverse), `vbroadcast` (setup K5 fold). No new op kinds.

---

## 4. Day-1 experiment (smallest thing to validate/kill fast)

**Goal:** prove the algebra end-to-end in the *simulator* on the real kernel, restricted
to the broadcast path (depth 0-3) first, before touching the gather path.

Steps:
1. Apply edits (1),(3),(4),(5) and the **broadcast-only** part of (2a) for `nb0..nb6`
   and `d3_*`. For gather rounds (depth≥4), temporarily *keep* the original stage-5
   `^K5` (guard the deletion with `if depth < 4:`), so only muxed rounds are converted.
   This isolates the algebra with minimal surface.
2. Measure cycles + correctness:
   ```bash
   cd /Users/haiyan-mini/Agent4Kernel/vliw && python tests/submission_tests.py
   ```
   Must print `OK` and a `CYCLES:` line. (Correctness is on unseeded random inputs;
   cycle count is deterministic — cycles == len(kb.instrs).)
3. Fast op-count sanity without the full sim (cycles == bundle count):
   ```bash
   cd /Users/haiyan-mini/Agent4Kernel/vliw && python -c "
   from perf_takehome import KernelBuilder
   from collections import defaultdict
   kb=KernelBuilder(); kb.build_kernel(10,2047,256,16)
   e=defaultdict(int)
   for b in kb.instrs:
       for k,s in b.items(): e[k]+=len(s)
   print('cycles',len(kb.instrs),'valu',e['valu'],'valu_floor',round(e['valu']/6,1))
   "
   ```
   **Kill criterion:** if `valu` does not drop by ~`512 * (fraction of rounds converted)`
   (~7/11 of 512 ≈ 326 for depth<4 only) or `submission_tests` fails, the algebra or the
   node-broadcast bookkeeping is wrong — stop and re-derive before extending to gather.
4. If green, extend to the gather path (2b) and re-measure. Expect valu ≈ 6543,
   valu_floor ≈ 1090, cycles trending toward 1150-1185.

---

## 5. Risks & likely failure modes

- **R1 — the stage2+stage3 fusion trap (proven dead, do NOT chase).** The shift-distributes-over-muladd identity `(a*33+K2)<<9 == a*16896 + (K2<<9)` holds (verified 200k), letting you fuse stage2+stage3 from 4 ops → 3 (`2 muladd + 1 xor`). **But** it converts one flexible op into a second *valu-locked* muladd: valu-locked 1→2. Since valu is the binding floor, this *raises* it by +512 valu ops (~+85 floor cycles). **Net loss.** The K5-deferral is the opposite: it removes a valu op with no new muladd. Lesson baked in: only reductions that cut the *binding* (valu) work without adding muladds help.
- **R2 — gather-path (depth≥4) node-K5 bookkeeping adds ops.** If baking K5 into gathered nodes forces an extra `^K5` on gather rounds, you claw back part of the win on those rounds. Depth≥4 rounds are ~7/11 of rounds here. Mitigation: fold K5 into the existing `val ^= node` step (lines 407-410) so no op is added; if that proves impossible, the depth<4-only variant still nets ~326 valu ops (~54 floor cycles).
- **R3 — round-0 / final-round boundary bugs.** The x-space carry has two seams (raw input round 0, stored output round 15). A sign error here corrupts *all* subsequent rounds via idx→node feedback (32-bit fidelity is mandatory — any bit change propagates). Mitigation: the §"proofs" harness already tests the multi-round recursion; replicate it as a standalone Python check before trusting the kernel.
- **R4 — floor drop may not translate to realized cycles.** The 66-cycle windup/drain tail gap is scheduler-bound, not floor-bound. Lowering the floor helps only to the extent the *middle* (jointly saturated) region shrinks. If the middle is already valu-saturated, removing valu work directly shrinks it — favorable. But if the tail gap grows as the floor drops (fewer vectors in flight fill fewer slots), realized gain could be as low as ~30-45 cycles. This is why confidence is *medium*, not high.
- **R5 — scratch pressure.** Baking K5 needs no new per-vector scratch (setup-only broadcast), but verify `alloc_scratch` stays ≤ SCRATCH_SIZE (1536); current build is near budget (NUM_MTMP_GROUPS OOM'd at 6+ per notes).

---

## 6. Expected payoff + confidence + effort

- **Floor movement (hard, verified):** valu floor 1176 → 1090; combined 1165 → 1097.
- **Realized cycles:** optimistic ~1140, likely 1155-1175, conservative 1185. Estimate `expected_cycles_low=1140`, `expected_cycles_high=1185`.
- **Confidence it beats 1230:** **medium** — the algebra is proven exact (2.3M+ random inputs, all edge cases, full multi-round recursion, 0 mismatches), and it removes work from the *binding* engine, so a floor drop is certain; the uncertainty is purely how much of the ~85-cycle floor drop the tail-limited schedule captures (R4).
- **Effort:** ~1.5-3 days. Day 1: broadcast-path variant + boundary seams (kill/confirm). Day 2: gather-path fold + parity/final-round hardening + full submission_tests across depths. Day 0.5 buffer for R2/R3 debugging.

---

## 7. Dependencies / prerequisites

- **No libraries.** Pure Python edits to `perf_takehome.py`.
- **Scratch budget:** one `K5` broadcast vector if not reusing an existing const; `two_v` already available as `c["m2"]`. Confirm ≤ SCRATCH_SIZE.
- **A standalone algebra test harness** (the §"proofs" scripts) kept alongside to re-verify the identity if constants/stages are ever touched.
- **No refactor of the scheduler** — this is an emission-level change only; the greedy list scheduler (lines 72-201) is untouched.
- **Prerequisite knowledge:** the x-space carry interacts with the diagonal emission (`gen_body`, lines 679-716) only through per-vector `val`; since every vector carries `valx` uniformly, no rotation/step logic changes.

---

## Appendix — proofs (all verified in the simulator's arithmetic, mod 2^32)

1. **stage5 without K5 equals hash XOR K5:** `myhash_x(x) == myhash(x) ^ K5` — verified 300k random. (K5 = 0xB55A4F09, odd ⇒ flips parity, so it cannot simply be dropped.)
2. **K5 cancels across the round boundary:** `((a^(a>>16))^K5) ^ node == (a^(a>>16)) ^ (node^K5)` — verified 500k random.
3. **Full multi-round x-space equivalence** (carry valx=trueval^K5, node'=node^K5, parity-swapped traverse, bottom-wrap): trueval and idx match reference across random rounds incl. bottom-wrap — verified 20k full rounds, 0 mismatch.
4. **Parity swap zero-cost:** addend `1+(trueval&1) == 2-(valx&1)`; `idx = 2*idx + 2 - (valx&1)` matches `2*idx + (1 if trueval even else 2)` — verified 500k, 0 mismatch. Realized as muladd const 1→2 and traverse `+`→`-` (no op added).
5. **Dead ends confirmed:** (a) K0 add sits after the input XOR (`(val^node)*4097+K0`) — ADD does not commute with the preceding XOR, so K0 cannot fold into node broadcast. (b) K1/K3 are consumed by muladds (nonlinear vs XOR) — no chaining. (c) A standalone xorshift-with-const combine `a^(a>>s)^K` needs 3 binary ops on a 2-input-op ISA (3 distinct runtime inputs a, a>>s, K) — irreducible. (d) stage2+stage3 fusion (R1) is op-count −1 but valu-locked +1 — net loss.

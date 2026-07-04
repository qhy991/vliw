# Direction: Hash op-count reduction via stage-5 K5-deferral (x-space carry)

> Assigned lane: *REDUCE the total op count of the hash itself* — attack the
> 7055-valu / 13456-alu totals directly, lowering ALL floors.

---

## 1. Direction name + one-line thesis

**Name:** Stage-5 K5-deferral (carry `valx = trueval ^ K5` across rounds; bake K5 into node broadcasts).

**Thesis:** The hash's final combine stage-5 = `(a ^ K5) ^ (a >> 16)` spends **one valu op per (vec,round)** on the constant term `t1 = a ^ K5` (line 426, `self.v_alu("^", node, val, c["K5"])`). Because that `^ K5` lands at the hash/round boundary — immediately adjacent to the next round's `val ^ node` — it can be **algebraically deferred**: carry `valx = trueval ^ K5` between rounds and fold `K5` once into every node-broadcast constant.

> **REVIEW CORRECTION (validated in the simulator):** the original draft claimed 512 valu
> ops deleted (floor 1176→1090). That over-counts. The deferral is only free when the
> **next** round's node comes from a *broadcast* (depth 0-3) — broadcasts can carry a baked
> `^K5` at setup for ~15 one-time ops. When the next round is a **gather** (depth>=4), the
> node comes from memory and cannot be pre-baked; deferring across that boundary re-adds one
> `^K5` per (vec,round), exactly cancelling the deletion. Rounds whose successor is a
> broadcast round are `r ∈ {0,1,2,10,11,12,13}` (successors at depths {1,2,3,0,1,2,3}) —
> **7 of 16 rounds**, so the true net deletion is `7 * 32 = 224 valu ops`, not 512. The
> "full deferral + gather fixup" variant nets the *same* 224 (−480 deleted, +256 re-added),
> so the selective 7-round variant strictly dominates: same win, far smaller blast radius.
> Corrected floors: valu `7055-224 = 6831 → 1138.5` (was claimed 1090); combined
> `(6831 + 13456/8)/7.5 ≈ 1135` (was claimed 1097). Still the single largest verified
> floor-lowering lever, but ~40 cycles smaller than originally advertised.

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

**The lever (corrected).** `t1 = a ^ K5` in stage-5 is emitted as `v_alu` (line 426) = a genuine **valu** op, one per (vec,round). Deferral is valid (and free) exactly on the rounds whose **successor** takes its node from a K5-baked broadcast — `r ∈ {0,1,2,10,11,12,13}` — netting `7 * 32 = 224` valu ops:

- valu: `7055 - 224 = 6831` → valu floor `6831/6 = 1138.5` (was 1176). **−37 cycles off the binding floor.**
- combined valu-equiv: `8737 - 224 = 8513` → `/7.5 = 1135` (was 1165). **−30 cycles off the combined floor.**

A bonus of the selective variant: round 15 (final) keeps its original `^K5`, so the stored output is already `trueval` — **the §3.5 output fixup becomes unnecessary** (0 extra ops instead of +32).

This is still the largest verified structural knob, because it removes work from the *binding* engine without adding any valu-locked muladd (contrast §5's trap). Realized cycles will not touch the floor — the ~56-cycle windup/drain tail gap persists — but lowering the *floor the schedule rides above* shrinks the tail-limited program too. If the ~4.6% tail-gap fraction holds, realized ≈ `1135 * 1.046 ≈ 1187`; conservatively 1195-1215, optimistically ~1180. **Stacks with the round-10 dead-idx elimination (see `11-dead-code-idx`), which removes a further 128 valu + 32 flow + 60+ load ops on an overlapping set of rounds — implement that first, it is hours not days.**

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

0. **THE GUARD IS ON THE *NEXT* ROUND'S DEPTH, NOT THE CURRENT ONE (critical).** Round r's
   trailing `^K5` determines the format of `val` *entering round r+1*; round r+1's node
   source determines whether the deferred K5 can be absorbed. So the deferral condition is
   `(r + 1) % h1 < 4 and r != rounds - 1` (successor is a broadcast/mux round), **not**
   `depth < 4`. Guarding on the current depth (as the original draft's Day-1 suggested)
   defers on rounds 3 and 14, whose successors (4 and 15) are gathers — the K5 is never
   re-absorbed and the kernel is silently wrong from round 4 onward. Thread the round
   number (or a `defer_k5` boolean) into `_emit_vec_round` alongside `skip_idx_update`.

1. **Delete the stage-5 t1 op** in `_emit_vec_round` (line 426) *on deferral rounds only*. Change:
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

2. **Bake K5 into the K5-carrying broadcast constants only.** The node comes
   from broadcasts `nb0` (line 544, depth-0), `nb1/nb2` (545-546, depth-1),
   `nb3..nb6` (554, depth-2), `d3_0..d3_7` (592, depth-3), and the gathered `node`
   for depth≥4 (lines 398-400).
   - **Broadcast path (depth 0-3):** after each `broadcast_scalar`, XOR the vector
     with a `K5` broadcast once at setup: `self.v_alu("^", nbk, nbk, c["K5"])`. This is
     ~15 setup ops total (one-time, negligible vs 224 saved). **Caveat:** rounds
     entered in *trueval* format also use these broadcasts (round 0 uses `nb0`;
     round 3/14 use `d3_*` after non-deferring predecessors... check per-round). In
     fact only the *successors of deferral rounds* need K5-baked tables. With deferral
     rounds `{0,1,2,10,11,12,13}`, the K5-baked consumers are depths {1,2,3,0} at
     rounds {1,2,3,11,12,13,14} — that is **all** uses of `nb1/nb2`, `nb3..nb6`,
     `d3_*`, and the round-11 use of `nb0`. The only trueval-format broadcast consumer
     is **round 0's `nb0`** — keep a second un-baked `nb0_raw` broadcast (+1 setup op)
     for round 0, or equivalently defer nothing into round 0 (it has no predecessor).
   - **Gather path (depth≥4): do NOT defer into it.** Deferring across a gather
     boundary costs +1 `^K5` per (vec,round), exactly cancelling the deletion (net 0,
     more code, more risk). The selective 7-round variant skips these rounds entirely.

3. **Parity swap in traverse — on deferral rounds only** (lines 432-441). A round whose
   `^K5` was deferred ends with `val = valx = trueval ^ K5`; K5 is odd, so
   `valx & 1 = (trueval & 1) ^ 1`. Reference addend `1 + (trueval&1)` becomes
   `2 - (valx&1)` (verified, 500k random, 0 mismatch). Rounds that keep their `^K5`
   (3..9, 14, 15) end in trueval format and keep the original traverse. Note round 10's
   traverse is dead code regardless (see `11-dead-code-idx`) — if that lands first,
   only rounds {0,1,2,11,12,13} need the swap. Zero extra ops — only constants/ops change:
   - depth-0 (line 438): `self.v_alu("+", idx, one_v, addr)` → `self.v_alu("-", idx, two_v, addr)` (idx = 2 - rem_x). Need a `two_v` broadcast (already exists as `c["m2"]`).
   - depth≥1 (lines 440-441): `v_muladd(node, idx, m2, one_v)` (2idx+1) → `v_muladd(node, idx, m2, two_v)` (2idx+2), then `v_alu("+", idx, node, addr)` → `v_alu("-", idx, node, addr)` (idx = i2p2 − rem_x). Same op count.
   - `rem = val % 2` (line 432) is unchanged: `rem_x = valx % 2`.

4. **Round-0 input boundary.** Round-0 reads raw `val` from mem (vload, line 663) —
   trueval format — and round 0 is not a deferral *target* (it has no predecessor), so
   its hash input must be `trueval ^ tree[0]`. Use the un-baked `nb0_raw` broadcast for
   round 0 and the K5-baked `nb0` for round 11 (whose predecessor round 10 defers).
   One extra setup broadcast, zero per-round ops.

5. **Final-round output fixup: NOT NEEDED in the selective variant.** Round 15 is not a
   deferral round (it is final), so it keeps its original `^K5` and stores `trueval`
   directly. Net: exactly `−224` valu ops, `+~17` one-time setup ops.

**ISA ops used:** `^`, `>>` (v_alu), `multiply_add` (v_muladd, unchanged count), `-`
(v_alu, replacing `+` in traverse), `vbroadcast` (setup K5 fold). No new op kinds.

---

## 4. Day-1 experiment (smallest thing to validate/kill fast)

**Goal:** prove the algebra end-to-end in the *simulator* on the real kernel, using the
selective 7-round variant directly (it is the final form — there is no profitable
"extend to gather" phase 2).

Steps:
1. Apply edits (0),(1),(2),(3),(4): defer on rounds `{0,1,2,10,11,12,13}` — i.e. guard
   with `defer = (r != rounds-1) and ((r+1) % h1 < 4)`, threading `r` into
   `_emit_vec_round`. **Do NOT guard on the current round's `depth < 4`** — that defers
   on rounds 3/14 whose successors are gathers and silently corrupts every value from
   round 4 onward (the original draft's Day-1 had this bug).
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
   **Kill criterion:** if `valu` does not drop by exactly **224** (7 deferral rounds × 32
   vec) or `submission_tests` fails, the deferral-round set or the node-broadcast
   bookkeeping is wrong — stop and re-derive. Expect valu ≈ 6831, valu_floor ≈ 1138.5.
4. Do **not** extend to the gather path — it is provably net-zero (+1 `^K5` per deferred
   gather round exactly cancels the deletion). If green, re-sweep `_combine_head/_tail`
   against the new op profile and measure the realized cycle count.

---

## 5. Risks & likely failure modes

- **R1 — the stage2+stage3 fusion trap (proven dead, do NOT chase).** The shift-distributes-over-muladd identity `(a*33+K2)<<9 == a*16896 + (K2<<9)` holds (verified 200k), letting you fuse stage2+stage3 from 4 ops → 3 (`2 muladd + 1 xor`). **But** it converts one flexible op into a second *valu-locked* muladd: valu-locked 1→2. Since valu is the binding floor, this *raises* it by +512 valu ops (~+85 floor cycles). **Net loss.** The K5-deferral is the opposite: it removes a valu op with no new muladd. Lesson baked in: only reductions that cut the *binding* (valu) work without adding muladds help.
- **R2 — RESOLVED BY REVIEW: the gather path is net-zero, skip it.** Baking K5 into gathered nodes necessarily costs +1 `^K5` per deferred-into gather round (there is no 3-input XOR, and rewriting the tree in memory at setup costs ~2047 load+store pairs ≈ 1000+ setup cycles — dead). Full deferral nets −480 + 256 = −224, identical to the selective 7-round variant. The selective variant is the final form.
- **R3 — round-0 / final-round boundary bugs.** The x-space carry has two seams (raw input round 0, stored output round 15). A sign error here corrupts *all* subsequent rounds via idx→node feedback (32-bit fidelity is mandatory — any bit change propagates). Mitigation: the §"proofs" harness already tests the multi-round recursion; replicate it as a standalone Python check before trusting the kernel.
- **R4 — floor drop may not translate to realized cycles.** The 66-cycle windup/drain tail gap is scheduler-bound, not floor-bound. Lowering the floor helps only to the extent the *middle* (jointly saturated) region shrinks. If the middle is already valu-saturated, removing valu work directly shrinks it — favorable. But if the tail gap grows as the floor drops (fewer vectors in flight fill fewer slots), realized gain could be as low as ~30-45 cycles. This is why confidence is *medium*, not high.
- **R5 — scratch pressure.** Baking K5 needs no new per-vector scratch (setup-only broadcast), but verify `alloc_scratch` stays ≤ SCRATCH_SIZE (1536); current build is near budget (NUM_MTMP_GROUPS OOM'd at 6+ per notes).

---

## 6. Expected payoff + confidence + effort

- **Floor movement (hard, corrected by review):** valu floor 1176 → 1138.5; combined 1165 → ~1135. (The original 1090/1097 claim double-counted the gather rounds.)
- **Realized cycles:** optimistic ~1180, likely 1190-1210, conservative 1220. Estimate `expected_cycles_low=1180`, `expected_cycles_high=1220`. Stacked with `11-dead-code-idx` (−128 valu / −32 flow / −60 load, orthogonal rounds), combined floor drops to ~1118 and realized ~1165-1200 is plausible.
- **Confidence it beats 1230:** **medium-high** — the algebra is proven exact (2.3M+ random inputs, all edge cases, full multi-round recursion, 0 mismatches), and it removes work from the *binding* engine, so a floor drop is certain; the uncertainty is purely how much of the ~37-cycle floor drop the tail-limited schedule captures (R4).
- **Effort:** ~1-2 days. Day 1: selective 7-round variant + boundary seams + correctness (kill/confirm). Day 2: re-sweep `_combine_head/_tail` against the new op profile, harden, measure. (The gather-path phase from the original plan is deleted — it is net-zero.)

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

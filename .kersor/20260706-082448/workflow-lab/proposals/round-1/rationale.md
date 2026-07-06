# Rationale — vliw-d3d4-joint-anneal (round-1 fork variant)

## Why the base workflow was selected

The round-1 selection (`round-1-selection.json`) picked `vliw-sparse-mask-search`
as the on-axis candidate: it is the only eligible catalog workflow whose
description targets the exact levers this session exists to search —
`D3_GATHER_MASK / D4_COLD_MASK / const_flow`. The round-0 transfer item 1
(explore, evidence=user_provided) names the joint `D3_GATHER_MASK x D4_COLD_MASK`
search as the live axis, with the measured decomposition d3-alone -4, d4-alone
-18, both -32 on the load engine. Transfer item 4 (reuse) gives the shipped
1120 champion mask values to seed from. The sibling `vliw-anneal-optimizer`
was the fallback but is off-axis: its `whenToUse` restricts it to
combine/extract/offset/const_flow/xor engine-assignment masks and does not
touch the d3/d4 gather/cold masks.

## The precise gap / stalled evidence justifying the variant

The base workflow's method is a **single-position sweep + size-2/3 combination
search** over the benefit window. Round-0 transfer item 2 (failed_strategy,
evidence=user_provided) records that this method **stalls at the 1132 local
optimum**: the shipped 1120 champion needs **full-space simulated annealing**
(64-bit bit-flip spanning both d3 rounds), which the sweep+combo method cannot
reach. The fit-judge reason is explicit: the levers are exactly right, but the
*method* is wrong — prefix-k on d3/d4 is NO-GO, and the synergy (d3 is worth
-4 alone but -14 on top of d4) is invisible to any single-axis or
small-combination search. Only a joint full-space SA that co-perturbs both
64-bit masks together can capture the -32 synergy.

This is a contract/method adaptation, not a freeform rewrite: the levers, the
correctness gates, and the return envelope are preserved; only the search
method is escalated from sweep+combo to joint full-space SA.

## Every source-level change made

The variant is a fork of `vliw-sparse-mask-search` that adopts the
`vliw-anneal-optimizer` orchestration shape (the authored sibling that already
orchestrates a Python SA driver via Bash). Concretely:

1. **meta**: new unique name `vliw-d3d4-joint-anneal`; new description/whenToUse
   scoped to the joint d3xd4 synergy axis and the stall-at-1132 gap; new phase
   list (Orient / Joint-SA / Verify+land) replacing sweep/combo/verify.

2. **Inlined scaffolding (verbatim)**: the `__unwrapArgs` arg_guard block and
   the `agentRetry` / `expect` / `guard` scaffolding are copied verbatim from
   `vliw-anneal-optimizer` (Workflow runtime parses bare scripts; static
   imports are rejected).

3. **args contract**: replaced the base's `probe_cmd` / `verify_cmd` /
   `n_positions` / `combo_sizes` contract with the SA-driver contract:
   `project_root` (required), `exp_dir`, `iters` (2500), `restarts` (3),
   `seed` (42), `best_known` (1120), `pspace0_bound` (1187), `collect` (1128),
   `topk` (50), `model_mechanical` (haiku), `model_judgment` (sonnet).

4. **Phase 1 Orient**: reads `directions/LESSONS.md` and measures the baseline
   for BOTH configs via `parity_check.py && algebra_check_ported.py &&
   tests/submission_tests.py` (PSPACE=1) and `PSPACE=0 python
   tests/submission_tests.py`. (Faithful to `vliw-anneal-optimizer` Orient;
   the base workflow had no Orient phase.)

5. **Phase 2 Joint-SA**: dispatches a mechanical agent to run
   `python experiments/anneal_d3d4_joint.py --iters --restarts --seed --collect
   --topk --gate1 --gate0 --out --pareto` and read the champ JSON
   (`best_full1`, `best_full0`, `d3`, `d4`, `verdict`). The driver seeds itself
   from the shipped 1120 champion masks (`D3_CHAMP` / `D4_CHAMP` constants in
   the driver). This mirrors how `vliw-anneal-optimizer` orchestrates
   `omni_anneal.py`.

6. **Phase 3 Verify+land**: dispatches an agent to (a) inject the champ masks
   via `D3_GATHER_MASK` / `D4_COLD_MASK` env vars and run the full dual gate
   (parity + algebra + submission_tests for PSPACE=1 and PSPACE=0); (b) ONLY if
   landable, edit `perf_takehome.py` shipped defaults — the `_d3champ` tuple
   near line 459 and the d4 default tuple near line 486 — and re-run the gate
   on the shipped-source build to confirm reproduction. This goes one step
   beyond the base/sibling Verify (which only gates) by actually landing the
   champ into the shipped source, because the session's purpose is to ship a
   new d3xd4 champion.

7. **Return envelope**: keeps the base's `overall_speedup` /
   `best_kernel_code` / `landed`-style fields. `best_kernel_code` serializes
   the `{d3, d4}` champ masks (the optimized artifact for this VLIW scheduler
   is the mask pair, not GPU source). `overall_speedup = baseline /
   pspace1_cycles` when landable, else null. Added fields: `champ_d3`,
   `champ_d4`, `driver_full1`, `driver_full0`, `driver_verdict`,
   `edited_perf_takehome`, `shipped_confirmed`, `failed_clause`.

## Why the variant remains compatible with KerSor's evidence/return contract

- **Same speedup_field / best_kernel_field** as the base
  (`overall_speedup` / `best_kernel_code`), as required by the evolution goal.
- **NON-REMOVABLE dual landability gate preserved verbatim**: PSPACE=1 correct
  AND < best AND PSPACE=0 correct AND <= 1187. The driver applies it
  internally; the workflow RE-VERIFIES it on the env-injected build and
  RE-CONFIRMS it on the shipped-source build. The gate is not relaxed.
- **Arithmetic-identity gates preserved**: `parity_check.py` and
  `algebra_check_ported.py` run on every champ in Phase 3. Masks only reroute
  mux<->gather / gather<->vload; the arithmetic graph is unchanged by
  construction, but the gates still run — they are NOT removed.
- **tests/ untouched**: the workflow explicitly forbids modifying tests/.
- **No forbidden APIs**: no `Date.now()`, `new Date()`, `Math.random()`, or
  `performance.now()`. All randomness lives inside the seeded Python driver.
- **No harness manipulation**: the Phase-3 prompt explicitly forbids
  free-pool-scrubbing / zeroed-tensor pre-allocation / reference-allocator
  tricks; the champ must win on real measured cycle count.
- **No non-determinism in the workflow layer**: the driver is seeded
  (`--seed ${SEED}`); model routing is the only nondeterministic element, which
  is the same as the sibling authored workflow.

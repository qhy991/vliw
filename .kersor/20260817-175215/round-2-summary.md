# Round 2 Summary

## Workflow Run

- Workflow: vliw-bundle-packing-optimization-2 (re-selected via deterministic fallback; only catalog entry)
- Speedup Achieved: 21.423143851508122x (147734/6896 cycles, deterministic per test-method.md rule 9)
- Convergence: converged (failure_class=none)
- Best Kernel: best-kernel/best.py (source: workflow-authoring/candidates/candidate-1/perf_takehome.py)
- Correctness: PASSED — exit 0, unittest "Ran 1 test ... OK", 8/8 iterations each printing CYCLES: 6896
- Benchmark: exit 0, exactly one anchored `CYCLES: 6896` line; verify-candidate hash_matches=true
- Usage: 740,072 total tokens (713,978 input / 504,064 cached / 26,094 output; budget charge 183,587), dispatch wall 484.34 s, no GPU time (CPU-hosted simulator). Run resumed after an external SIGTERM kill: 3 turns replayed free; correctness/benchmark/verify executed live.

## Cross-Round Comparison

| Round | Workflow | Speedup | Status |
|---|---|---:|---|
| 1 | vliw-bundle-packing-optimization-2 | null (incumbent 1.0x) | correctness_mismatch (fail-closed) |
| 2 | vliw-bundle-packing-optimization-2 | 21.4231x | converged |

## Current Best

- Workflow: vliw-bundle-packing-optimization-2
- Speedup: 21.423143851508122x vs the frozen 147,734-cycle session baseline (incumbent 1.0x; best_improved=true)
- Kernel: best-kernel/best.py
- SHA-256 binding: the returned `best_kernel_code` string hashes to 78993c2963b0ad838a858add2ea056b7294e425b6807f963cad7a91bac6c3b11 == candidate-1/perf_takehome.py on disk == claimed `candidate_hash`. best.py differs from that string only by the materializer's one appended trailing newline (11408 vs 11407 bytes, documented in run-2/analysis.md); a post-hoc clean-copy re-verification in a fresh layout reproduced exit 0, 8/8 at CYCLES: 6896.
- Strategy: dependency-aware VLIW bundle packing + VALU vectorization. `build(..., vliw=True)` greedily packs the already-topologically-ordered slot stream without ever reordering, placing a slot in the current bundle only when its engine has capacity (alu=12, valu=6, load=2, store=2, flow=1) and its scratch reads/writes have no RAW/WAR/WAW overlap with already-placed slots; debug slots act as barriers so observers see committed values. The batch tiles into 32 groups of VLEN=8 lanes; contiguous loads (vload), hash stages, parity/child selection, bounds wrapping, and stores (vstore) run on the VALU with constants deduplicated via `scratch_const`/`vector_const`. The data-dependent forest lookup has no vector gather in the ISA, so it stays 8 scalar address ALU ops + 8 scalar loads per group — gathered into one contiguous scratch range consumed as a vector downstream.

## Transferable Insights

- win-1 (validated_win, reuse, measured/benchmark): the dependency-aware packing + VALU vectorization combination above — 147734 -> 6896 cycles (21.4231x against a target of 8.0x). Technique: instruction_scheduling.
- ins-2 (bottleneck, explore, inferred/benchmark): the residual gap (measured 6896 vs the unverified ~2139-cycle Aug-18 design claim) is dominated by the scalar gather — 8 scalar loads per group against the 2-slot load engine, across 32 groups x 16 rounds. Levers: forest-value caching across repeated indices, load_offset address folding, cross-group gather/vector interleaving. Technique annotated by the synthesizer: recompute_vs_store.
- con-1 (search_constraint, constrain, measured/correctness): the kernel assumes batch_size % VLEN == 0 (unmasked vload/vstore, no tail group); verified only at batch_size=256. A masked/scalar tail is required before reuse at other batch sizes, and scratch sizing must be re-derived if rounds/groups change.
- env-1r (env_fact, gate, measured/runtime): the round-1 interpreter gate is resolved — absolute /Users/haiyan-infiniai/homebrew/bin/python3 on both eval commands produced a clean run; keep the pin in all future rounds.

## Dedup and Carry-Forward Choices

- env-1 vs env-1r: the transfer schema (docs/transfer-object.md) defines no superseded/supersedes field, so both are kept with their original verbatim content — env-1 (r1: the login-shell python3 -> 3.9.6 SyntaxError diagnosis) and env-1r (r2: the measured resolution confirming the pin works). `env_fact` items never expire within a session (dedup rule 3), and the normalized claims differ, so they do not collapse; env-1r is the operative gate for any future round.
- All five round-0 user_provided priors (ins-exp-1..5) carried forward unchanged: they are backend=cuda scoped with no overlap with this python-simulator task's measured items, so no measured-vs-prior conflict rule fires.
- ins-r1d-1 (hypothesized, ~2139-cycle design intent) kept alongside ins-2 (inferred, measured 6896 + mechanism): numeric metrics inside claims are not normalized away — both data points stay visible to the promote layer.
- Round-1's fail-1 (avoid: bare-class emission without the `from problem import ...` preamble) and ins-1 (r1 bottleneck diagnosis, now realized by win-1) kept verbatim.
- No score-only validated_win items to drop (win-1 names its mechanism). Synthesizer annotations touched only the optional `technique` field (win-1's came from the source; ins-2's was added here) — no claim or hint text was rewritten.

## Round-1 Directive Follow-Through

- env-1 (gate): honored — both eval commands pinned to the absolute Homebrew python3; correctness ran clean.
- fail-1 (avoid): honored — candidate-1 is a complete module starting `from problem import HASH_STAGES, SCRATCH_SIZE, VLEN`.
- ins-r1d-1 (explore): honored — the 32x8-lane vectorized design was re-derived and realized as a measured 6896 cycles (vs the unverified ~2139 claim; still 21.42x >= the 8.0x target).

## Failed Strategies

- None this round. Round-1's fail-1 was fixed, not repeated.

## Contract Warnings

- `ins-exp-2` (round-0 user_provided failed_strategy, "CUBLAS_COMPUTE_16F broken on sm_89") carries an empty `actionable_hint` (< 30 chars). Carried forward as-is per the do-not-rewrite rule so the promote-side `weak_hint` gate can drop it (`validate-transfer.sh --strict` warns, never fails). `ins-exp-1` also has an empty hint but is `workflow_compatibility`, not `failed_strategy`, so it is outside that hard rule.
- Validation result: `TRANSFER_VALIDATION=ok (13 item(s))`, exit 0, one STRICT_WARN (the ins-exp-2 hint above); normalize-transfer.py applied and idempotent. No evidence-pair violations (measured never pairs with llm_inferred/profile_heuristic), no anti-list fine-schedule tokens in any prescriptive-kind claim.

## Decision

COMPLETE: the measured, evidence-bound win of 21.4231x (147734 -> 6896 cycles, deterministic ratio, correctness PASSED 8/8, anchored benchmark, hash-bound candidate) exceeds the session target_speedup of 8.0 by 2.68x, with best_improved=true over the 1.0x incumbent and the best kernel materialized and re-verified in a clean layout; round-1 directives were all honored, and residual headroom (ins-2, the scalar-gather bound) is optimization-beyond-target, not unmet objective — per Phase 7 the Stop hook's acceptance gate now adjudicates this decision, and a reject there would downgrade to CONTINUE as the hook's prerogative.

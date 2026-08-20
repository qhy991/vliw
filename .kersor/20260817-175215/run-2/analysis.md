# Run Analysis

## Parseable Fields

- Workflow: vliw-bundle-packing-optimization-2
- Best Speedup: 21.423143851508122
- Metric: cycles
- Baseline ID: cycles-self
- Baseline Latency (ms): 147734 (cycles; self-referential session baseline)
- Candidate Latency (ms): 6896 (cycles)
- Harness Command: python -c "from tests.submission_tests import cycles; print('CYCLES:', cycles())"
- Best Kernel Path: best-kernel/best.py
- Has Best Kernel: true
- Iterations Completed: 8
- Convergence Status: converged
- Raw Speedup Field: overall_speedup
- Raw Speedup Value: 21.423143851508122
- Compiled: true
- Correct: true
- Infrastructure Failure: false
- Incumbent Speedup: 1.0
- Candidate Speedup: 21.423143851508122
- Best Improved: true
- Candidate Source: workflow-authoring/candidates/candidate-1/perf_takehome.py
- Bottleneck Class: unknown (CPU-hosted VLIW simulator; roofline/matrix-lever layer not applicable)
- Achieved Matrix Util: null

## Contract Check

- Speedup equals baseline/candidate: 147734 / 6896 = 21.423143851508122 — matches `overall_speedup` exactly (deterministic per test-method.md rule 9, never taken from the agent report).
- Session target_speedup=8.0 (target cycles ~18467): 6896 cycles is 2.68x the target — EXCEEDED.
- Metric contract complete: metric_name, baseline_id, harness_command, both latencies present, so the round is eligible for headline best (compiled=true, correct=true).

## Verification Evidence

- Correctness agent: exit 0, passed=true, unittest "Ran 1 test ... OK", 8/8 kernel iterations each printing CYCLES: 6896 (forest_height=10, rounds=16, batch_size=256).
- Benchmark agent: exit 0, cycles=6896, cycles_found=true, stdout contains exactly one anchored `CYCLES:` line plus the harness's own echo.
- verify-candidate: hash_matches=true — SHA-256 78993c2963b0ad838a858add2ea056b7294e425b6807f963cad7a91bac6c3b11 binds output.json `best_kernel_code` == on-disk candidates/candidate-1/perf_takehome.py == `candidate_hash`.
- Materialized best-kernel/best.py differs from the returned code string by exactly one materialization-added trailing newline (11408 vs 11407 bytes); the RETURNED string hashes to the claimed 78993c29... Post-hoc clean-copy re-verification reproduced correctness exit 0 (8/8, 6896) and CYCLES: 6896 -> 21.423x.

## Winning Strategy

Dependency-aware VLIW packing + VALU vectorization:

- `build(..., vliw=True)` greedily packs the already-topologically-ordered slot stream, never reordering. A slot joins the current bundle only when its engine has capacity (alu=12, valu=6, load=2, store=2, flow=1) and its scratch reads/writes have no RAW/WAR/WAW overlap with slots already placed; otherwise the bundle flushes. Debug slots are barriers so correctness observers see committed values.
- The batch is tiled into 32 groups of VLEN=8 lanes. Contiguous index/value loads (vload), hash stages, parity/child selection, bounds wrapping, and stores (vstore) are vectorized on the VALU; hash constants are deduplicated via `scratch_const`/`vector_const`.
- The forest lookup is data-dependent per lane and the ISA has no vector gather, so it stays as 8 scalar address ALU ops + 8 scalar loads per group — but the results land in one contiguous scratch range consumed as a vector by the VALU XOR/hash ops. The generated stream is phase-ordered across all groups.

## Bottleneck Insights

- Residual cost is dominated by the scalar forest gather: 8 scalar loads per group against a 2-slot load engine, across 32 groups x 16 rounds. Measured 6896 cycles vs the ~2139-cycle design intent claimed (unmeasured) for the Aug-18 32x8-lane schedule (see ins-2 for the follow-up lever set).
- Not applicable: GPU roofline / matrix-unit utilization (backend=python, no GPU).

## Failed Strategies

- None this round. (Round-1's fail-1 — bare class body without the `from problem import ...` preamble — was fixed: candidate-1 starts with `from problem import HASH_STAGES, SCRATCH_SIZE, VLEN` and passed correctness.)

## Transfer Items

- win-1 (validated_win, reuse, measured/benchmark): VLIW dependency-aware packing + VALU vectorization with scalar forest gathers into contiguous scratch ranges — 147734 -> 6896 cycles (21.4231x). technique=instruction_scheduling.
- env-1r (env_fact, gate, measured/runtime): round-1 env-1 interpreter pin RESOLVED — absolute /Users/haiyan-infiniai/homebrew/bin/python3 on both eval commands produced a clean correctness run; keep the pin in all future rounds.
- con-1 (search_constraint, constrain, measured/correctness): kernel assumes batch_size is VLEN-aligned (unmasked vload/vstore, no tail group); verified only at batch_size=256. Add a masked/scalar tail before reuse at other batch sizes.
- ins-2 (bottleneck, explore, inferred/benchmark): scalar gather bound — no vector gather in the ISA; attack via forest-value caching, load_offset address folding, cross-group gather interleaving.

## Round-1 Directive Follow-Through

- env-1 (gate): honored — both commands pinned to absolute Homebrew python3; correctness ran clean.
- fail-1 (avoid): honored — candidate emitted as a complete module with the problem-import preamble.
- ins-r1d-1 (explore): honored — the 32x8-lane vectorized design was re-derived and realized as a measured 6896 cycles (vs the unverified ~2139 claim; still 21.42x >= the 8.0x target).

## Notes

- convergence_status=converged: the round produced a measured, correctness-verified win exceeding the session target_speedup=8.0. "converged" is the in-vocabulary canonical form — kersor_core/attempt.py `_CONVERGENCE_ALIASES` maps target_met/improved/success -> converged, and the closed set is {converged, budget_exhausted, stalled, error, unknown}.
- baseline_id=cycles-self: test-method.md has no external `Baseline:` field; the baseline is the session's own frozen cycle count (147734). The `*_latency_ms` fields carry cycle counts, not milliseconds (metric_name=cycles).
- Small-win reproduction gate skipped: 21.42x is far above the 1.10x noise band; the gate auto-passes large wins without repetition.
- Usage per .runtime/summary.json: 740,072 total tokens (713,978 input / 504,064 cached / 26,094 output), budget charge 183,587, dispatch_wall_seconds 484.34, no GPU time (simulator task). 6 calls total, 3 replayed on resume; correctness/benchmark/verify executed live.
- infrastructure_failure=false with no infra code: all phases completed, both commands exited 0; the outcome is an optimizer success, not an infra event.

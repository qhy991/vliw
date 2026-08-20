# Round 1 Summary

## Workflow Run

- Workflow: vliw-bundle-packing-optimization-2 (authored, probation)
- Speedup Achieved: null (correctness FAILED -> fail-closed; benchmark intentionally skipped)
- Convergence: error (failure_class=correctness_mismatch, failure_domain=candidate)
- Best Kernel: workflow-authoring/candidates/candidate-0/perf_takehome.py (SHA-256 ca8524... verified on disk; NOT a winner — incorrect)
- Iterations: 1; 4 agent calls, all phases completed (Analyze -> Bundle-And-Vectorize -> Evaluate -> Report); 662,130 tokens, 872 s dispatch wall, no GPU time (simulator task)

First fully-successful mechanical execution of this session (prior attempts: v1/v2 authoring issues, v3 died on EVAL_DIR ReferenceError mid-prompt). Evidence integrity held: exclusive eval dir created, verbatim copies, SHA-256 binding verified post-hoc; infrastructure_failure=false.

## Cross-Round Comparison

| Round | Workflow | Speedup | Status |
|---|---|---:|---|
| 1 | vliw-bundle-packing-optimization-2 | null (incumbent 1.0x) | correctness_mismatch |

## Current Best

- Workflow: none (baseline incumbent 1.0x — 147,734 cycles, passes correctness 8/8)
- Speedup: none measured; candidate_latency_ms=null, overall_speedup=null per fail-closed contract

## Root Cause

The generated candidate was emitted WITHOUT its `from problem import (...)` preamble — the file starts at `class KernelBuilder:`, so SCRATCH_SIZE/VLEN/Engine/DebugInfo/HASH_STAGES are undefined -> NameError: SCRATCH_SIZE at perf_takehome.py:136 in the first build_kernel call. Candidate defect, not infrastructure. Second failure surface recorded in events.jsonl (SyntaxError at frozen_problem.py:222) is the eval interpreter resolving python3 to 3.9.6 under `/bin/zsh -lc`, which cannot parse the frozen problem's `match op:`; under Python 3.14 the same command reaches the candidate's own NameError (both reproduced post-hoc for diagnosis only). Two fixes: restore the preamble (candidate-side) and pin the eval interpreter >= 3.10 (workflow-side, env_fact env-1).

## Transferable Insights

- Starter kernel is fully scalar/serial vs 12 alu / 6 valu / 2 load / 2 store / 1 flow slots per cycle; the irregular per-lane forest gather (no gather/lane-extract op in the ISA) blocks full vectorization, so cross-lane VLIW packing around the scalar gather is the main cycle lever (ins-1).
- Derived: the Aug-18 interrupted dispatch's 13,677-byte 32x8-lane topological-list-schedule design (claimed ~2139 cycles, unverified — that dispatch died pre-eval) is the fastest re-derivation path once the preamble is restored (ins-r1d-1).
- Round-0 user priors (ncu blocked on this host, CUBLAS_COMPUTE_16F broken on sm_89, ksearch avoid, EVAL_BENCH_REF=false trap) carried forward unchanged — CUDA-scoped, no overlap with this python-simulator task's measured evidence.

## Failed Strategies

- fail-1: emitting the optimized kernel as a bare `class KernelBuilder:` file without the import preamble. The scheduler design itself (dependency scoreboard, per-lane scratch, hazard rejection) was never exercised past line 136 — nothing about its quality can be claimed.

## Contract Warnings

- `ins-exp-2` (round-0 user_provided failed_strategy, "CUBLAS_COMPUTE_16F broken on sm_89") carries an empty `actionable_hint` (< 30 chars) — carried forward as-is per the do-not-rewrite rule so the promote-side `weak_hint` gate can drop it (`validate-transfer.sh --strict` warns, never fails). All round-1 failed_strategy items carry non-empty hints; no evidence-pairing violations; no score-only validated_win items to drop.

## Decision

CONTINUE: fixable candidate defect (missing `from problem import (...)` preamble) with clear next-round transfer evidence (fail-1 + env-1 + ins-r1d-1) and remaining round budget — the next round must re-select/re-author emitting the COMPLETE module (preamble included), smoke-validated by `python3 -c "import ast; ast.parse(...)"` plus an import/1-round build_kernel check before invoking correctness, with the eval interpreter pinned to Python 3.10+ per env-1.

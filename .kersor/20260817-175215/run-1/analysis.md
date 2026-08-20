# Run Analysis

## Parseable Fields

- Workflow: vliw-bundle-packing-optimization-2
- Best Speedup: null (correctness FAILED -> fail-closed, no benchmark run)
- Metric: cycles
- Baseline ID: cycles-self
- Baseline Latency (ms): 147734 (simulator cycles; self-referential session baseline)
- Candidate Latency (ms): null (never measured)
- Harness Command: python -c "from tests.submission_tests import cycles; print('CYCLES:', cycles())"
- Best Kernel Path: workflow-authoring/candidates/candidate-0/perf_takehome.py
- Has Best Kernel: true
- Iterations Completed: 1
- Convergence Status: error
- Raw Speedup Field: overall_speedup
- Raw Speedup Value: null
- Infrastructure Failure: false (candidate defect, not infra)

## What Happened

This is the real round-1 run (the earlier `proposal_runtime_defect` analysis.json
in this directory was from the aborted v3 dispatch and is superseded by this
file). The re-authored workflow (`vliw-bundle-packing-optimization-2`, sha256
44b194f8...) ran end-to-end: Analyze -> Bundle-And-Vectorize -> Evaluate ->
Report, 4 agent calls, all completed (usage 662,130 total tokens, 872 s dispatch
wall). SHA-256 binding verified: candidate-0/perf_takehome.py on disk hashes to
ca85242791ee171d0b617f326c13414cbdfc96eba772d26a67263dd9aabdeac5, matching
output.json.

The candidate failed correctness with exit 1, so per the fail-closed evaluation
rules (test-method.md rule 10) `overall_speedup=null` and the benchmark was
never invoked. No post-generation measurement was made: the candidate is
incorrect, and the analyzer contract says a correctness-failing produced kernel
is not valid for measurement.

## Root Cause (verified post-hoc, diagnostic only)

The generated `perf_takehome.py` is a bare class body: the file starts at
`class KernelBuilder:`. The required module docstring and
`from problem import (Engine, DebugInfo, SLOT_LIMITS, VLEN, N_CORES,
SCRATCH_SIZE, Machine, Tree, Input, HASH_STAGES, ...)` preamble were dropped.
Every problem-module symbol is therefore undefined; the first
`KernelBuilder.build_kernel()` call dies at `alloc_scratch`:

```
NameError: name 'SCRATCH_SIZE' is not defined   (perf_takehome.py:136)
```

This is a candidate code defect. The infrastructure did what it was supposed to
do (exclusive eval dir, verbatim copies, SHA binding, exact command, fail-closed
result), so `infrastructure_failure=false` and no infra failure code is emitted.
Normalizer derives failure_class=correctness_mismatch -> failure_domain
"candidate", retry disposition change_candidate, solver cost bucket.

### Two failure surfaces, one failed check

- Recorded in events.jsonl: `SyntaxError: invalid syntax` at
  `frozen_problem.py:222` (`match op:`). The Evaluate correctness agent executed
  `/bin/zsh -lc 'python3 tests/submission_tests.py ...'`; in a login shell
  `python3` resolves to /usr/bin/python3 3.9.6, which cannot parse the 3.10+
  match statement the frozen problem uses. Under this invocation ANY candidate
  fails at import time, before its own code runs.
- Re-run under Python 3.14 (/Users/haiyan-infiniai/homebrew/bin/python3, the
  interpreter the canonical kernel passes under): the import succeeds and the
  failure becomes the candidate's own `NameError: SCRATCH_SIZE` at line 136.

Either surface fails the check, but they have different fixes: the preamble must
be restored in the candidate (candidate-side), and the eval interpreter should
be pinned >= 3.10 (workflow-side, recorded as env_fact `env-1` — under the
current login-shell PATH the correctness gate cannot distinguish a broken
candidate from a broken Python).

## Bottleneck Insights

- Starter kernel is fully scalar and serial: one engine slot per bundle, while
  the machine offers alu=12, valu=6, load=2, store=2, flow=1 per cycle (Analyze
  agent, llm_inferred).
- The irregular per-lane forest gather is the vectorization blocker: `vload`
  takes only a contiguous scalar address and the ISA has no lane-extract or
  gather op, so the realistic lever is cross-lane VLIW packing around the scalar
  gather plus valu for lane-wise hash/branch arithmetic (candidate's stated
  design; never exercised past line 136).
- Debug compares are free in cycle terms (debug engine uncounted when disabled)
  but act as ordering barriers for packing; the candidate kept them as separate
  zero-cycle bundles, which is sound.
- bottleneck_class: unknown — the deterministic roofline/matrix-unit layer does
  not apply to this CPU-hosted simulator task (no GPU, no matrix unit);
  achieved_matrix_util null.

## Failed Strategies

- fail-1: emitting the optimized kernel as a bare `class KernelBuilder:` file
  without the import preamble. The scheduler design itself (dependency
  scoreboard, per-lane scratch, hazard rejection) was never exercised past line
  136, so nothing about its quality can be claimed. Next candidate must ship the
  complete file and smoke-validate (`python3 -c "import perf_takehome"` plus a
  1-round build_kernel) before the correctness suite is invoked.

## Notes

- incumbent_speedup=1.0 (baseline 147,734 cycles passes correctness 8/8);
  candidate_speedup=null; best_improved=false.
- The Aug-18 sibling dispatch (13,677-byte kernel) claimed 2,139 cycles /
  ~69.1x with a fully vectorized 32x8-lane design, but that dispatch died at the
  workflow's EVAL_DIR ReferenceError before any eval dir was created, so the
  claim has no persisted candidate and no measured evidence — treat as
  unverified narrative, not a partial win (no exp_dir artifacts exist to
  scrape). Notably it required batch_size divisible by VLEN and used a
  topological list scheduler; if the preamble fix is made, re-deriving from that
  design is the fastest path.
- Usage from .runtime/summary.json (this run's completed workflow): 642,802
  input (470,528 cached) / 19,328 output / 662,130 total tokens; dispatch wall
  872.196 s; GPU time not applicable (simulator task).
- analysis.json is the producer artifact; `kersor-attempt.py normalize` consumes
  it to commit the canonical attempt-result.json (compiled=true — the file
  parses as Python; correct=false).

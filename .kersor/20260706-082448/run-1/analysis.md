# Run Analysis

## Parseable Fields

- Workflow: vliw-d3d4-joint-anneal
- Best Speedup: 1.0081
- Metric: cycles
- Baseline ID: merged-floor-1120
- Baseline Latency (ms): 1120
- Candidate Latency (ms): 1111
- Harness Command: python tests/submission_tests.py && PSPACE=0 python tests/submission_tests.py
- Best Kernel Path: {"d3":[0,1,2,3,4,34,35,44,45,50,54],"d4":[7,12,16,22,24,33,37]}
- Has Best Kernel: true
- Iterations Completed: 941
- Convergence Status: converged
- Raw Speedup Field: overall_speedup
- Raw Speedup Value: 1.0036
- Bottleneck Class: load_bound

## Bottleneck Insights

- Joint D3_GATHER_MASK x D4_COLD_MASK full-space SA landed 1120 -> 1111 cycles (PSPACE=1) / 1180 (PSPACE=0): tail-packing win on the load engine. The best mask has the highest load (1083.5, near un-masked 1087.5); the win comes from packing more work into load-constrained cycles, not reducing load.
- Load floor (~1083.5) still dominates over alu sub-floor (1036.7) by ~47 cycles. Sub-1111 progress requires a load-floor mover that ALSO improves tail scheduling -- a combined axis, not a pure load cut.
- Hard dual PSPACE gate confirmed: PSPACE=1 < 1111, PSPACE=0 <= 1180. rot-27 oracle validated as strict upper bound on full-32 realized.

## Validated Wins

- Joint D3xD4 full-space SA with dual PSPACE gate: 1120 -> 1111 cycles. Committed c31f27c, shipped in perf_takehome.py. Technique: full-space simulated annealing co-perturbing both masks (64-bit joint bit-flip space) with rot-27 oracle collection + full-32 confirm.

## Failed Strategies

- None this round (the dispatched workflow succeeded).

## Notes

- Speedup is a cycle-count ratio (deterministic, lower-is-better). Reproduction CV=0 trivially: same mask always produces same cycle count.
- No regime_breakdown: this is a single-metric VLIW scheduler, not a multi-shape GPU kernel.
- Metric contract baseline_id matches test-method.md 'Baseline: merged-floor-1120'. All contract fields present and valid.

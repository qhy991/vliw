# Round 1 Summary

## Workflow Run

- Workflow: vliw-d3d4-joint-anneal (evolved fork_variant v001 of vliw-sparse-mask-search)
- Speedup Achieved: 1.0081x (cycles: 1120 -> 1111, PSPACE=1)
- Convergence: converged (941 oracle iterations, 50 full-32 confirms)
- Best Kernel: run-1 session-best masks d3={0,1,2,3,4,34,35,44,45,50,54} d4={7,12,16,22,24,33,37}
- Committed: c31f27c, shipped in perf_takehome.py

## Cross-Round Comparison

| Round | Workflow | Speedup | Cycles (PSPACE=1) | Status |
|---|---|---:|---:|---|
| 0 | (user-prior seed) | 1.000x | 1120 | baseline champion |
| 1 | vliw-d3d4-joint-anneal | 1.0081x | 1111 | converged |

## Current Best

- Workflow: vliw-d3d4-joint-anneal
- Speedup: 1.0081x (cycle ratio 1120/1111)
- Kernel: run-1 session-best masks d3={0,1,2,3,4,34,35,44,45,50,54} d4={7,12,16,22,24,33,37}
- Strategy: Two-phase joint full-space SA — Phase-1 rot-27 oracle collection (cheap strict upper bound on full-32 realized), Phase-2 full-32 confirm with dual PSPACE landability gate. Co-perturbs both 64-bit masks (64-bit joint bit-flip space). Diverse HOT restarts decisive: 1111 found only by T0=3.5 seed 1337; T0=2.5 seed 42 bottomed at 1116.

## Transferable Insights

- The joint D3_GATHER_MASK x D4_COLD_MASK full-space SA is a measured win: 1120->1111, gate-passing and committed. Single-axis (d3-alone / d4-alone) search cannot see the coupling that produces the -41-cycle joint result.
- This is a TAIL-PACKING win, NOT a load-floor drop. The best realized mask (1111) has the HIGHEST load (1083.5, near un-masked 1087.5); the win packs more work into load-constrained cycles rather than reducing load. Pushing load down independently via more d4-cold HURTS realized cycles.
- Load floor (~1083.5) still dominates alu sub-floor (1036.7) by ~47 cycles. Sub-1111 progress requires a load-floor mover that ALSO improves tail scheduling — a combined axis, not a pure load cut.
- rot-27 oracle (0.33s) is a measured strict upper bound on full-32 realized (24/24 samples diff in [-144, 0]); usable as cheap search signal then full-confirm. Dual PSPACE gate (PSPACE=1 < best, PSPACE=0 <= 1187) is the landability contract.
- Diverse hot-start restarts are decisive for escaping the 1116 basin; a single seeded run under-explores.

## Failed Strategies

- (Carried from round-0 user prior, still valid) Single-position sweep + anchored combo search over d3 mask stalls at the 1132 local optimum; prefix-k on d3/d4 is NO-GO.
- (Round-1 process note, not a kernel strategy failure) The dispatched workflow's Verify+Land step overwrote the better committed 1111 with its own 1116 result; restored via git checkout. Future dispatches of this driver should preserve the session best or seed from it.

## Decision

CONTINUE: The d3xd4 joint mask axis is near-converged at 1111 (dense 1111-1119 plateau; further mask-only gains <1 cycle), but a different, untested axis with clear headroom remains: the load-floor mover that co-improves tail scheduling (ins-2 actionable_hint names D4_SCRATCH recycler rollup VLIW-25/VLIW-26 and D4_FREE engine-split VLIW-20 as candidate axes; roofline ceiling 814, realistic target ~1000, so ~111 cycles of headroom below 1111). The session has allow_workflow_evolution=true and allow_workflow_authoring=true, so a load-floor-axis variant can be evolved or authored for round 2 since all CUDA/AKW catalog workflows remain inapplicable (kernel_language=python, backend=python). The measured ins-2 bottleneck directive is the forward-looking explore item that a different workflow should act on.

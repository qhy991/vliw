# Round 1 Dispatch — vliw-d3d4-joint-anneal (evolved variant v001)

## Selected workflow
- Name: vliw-d3d4-joint-anneal (fork of vliw-sparse-mask-search)
- js_path: .kersor/20260706-082448/workflow-lab/variants/v001/workflow.js
- candidate_type: fork_variant, experimental (probation)
- Routed by: model (strategy-selector), after Phase 3.5 workflow evolution
- speedup_field: overall_speedup, best_kernel_field: best_kernel_code

## Why this workflow (fit-check → evolution chain)
1. select-workflow.sh shortlisted two authored VLIW-native workflows (all CUDA workflows correctly rejected: language=python).
2. strategy-selector picked vliw-sparse-mask-search (only on-axis levers: D3_GATHER_MASK/D4_COLD_MASK) with an explicit low-confidence caveat.
3. workflow-fit-judge: fits_task=false, fit_confidence=low — the base's single-position sweep + size-2/3 combo method is a known 1132 local optimum (round-0 transfer avoid directive); the 1120 champion required full-space SA; base also searches d3/d4 separately, missing the d3×d4 synergy (-32 vs -22 summed singles).
4. Phase 3.5 evolution: forked vliw-sparse-mask-search → vliw-d3d4-joint-anneal, replacing sweep+combo with a JOINT full-space SA (co-perturbs both masks, rot-27 oracle collection + full-32 confirm, dual PSPACE gate). Registered as variant v001.

## Method (driver: experiments/anneal_d3d4_joint.py)
- Phase-1: pure rot-27 oracle SA (~0.33s/build; oracle is a measured strict upper bound on full-32 realized — 24/24 samples diff∈[-144,0]) collecting distinct low-oracle joint masks.
- Phase-2: batch full-32 confirm of best masks; dual gate PSPACE=1 < 1120 AND PSPACE=0 <= 1187.
- Seed: shipped 1120 champion D3={0,1,2,3,4,37,39,40,46,54,58}, D4={25,26,27,29,31,34}.

## dispatch-args.json
project_root, exp_dir=run-1, iters=2500, restarts=3, seed=42, best_known=1120, pspace0_bound=1187, collect=1128, topk=50, models mechanical=haiku/judgment=sonnet.

## Resolver output
- resolved: exp_dir; missing_required: [project_root] (supplied = worktree root, trivially inferable under yolo, not a genuine must-ask).

## Handoff context
- Rendered from round-0-transfer.json (4 user-priors: joint-axis explore, sweep+combo avoid, dual-gate constrain, champion reuse). See run-1/handoff.txt.

## Note on parallel background search
Two diverse-seed instances of the same anneal_d3d4_joint.py driver were already launched (seed 42 T0=2.5, seed 1337 T0=3.5) before formal dispatch; seed 1337 reached oracle=1114 (guarantees full-32 <1120). The dispatched workflow runs its own seeded instance for protocol fidelity; the landed champion is cross-checked against all three.

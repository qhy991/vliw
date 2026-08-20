# Round 2 Dispatch Input

## Selected workflow
- vliw-bundle-packing-optimization-2 (re-selected via fallback; only catalog entry; round-2-selection.json committed)
- Prior evidence now in the loop: run-1 attempt_result (correctness_mismatch) + round-1 transfer (env-1 gate, fail-1 avoid, ins-1/ins-r1d-1 explore)

## Round-1 lessons baked into args
- env-1 (gate): eval commands pinned to absolute /Users/haiyan-infiniai/homebrew/bin/python3 (login shell resolves python3 → /usr/bin/python3 3.9.6 which SyntaxErrors on frozen_problem.py match-statement before any candidate code runs)
- fail-1 (avoid): candidate must be emitted as a COMPLETE module (module docstring + `from problem import (...)` preamble before `class KernelBuilder:`); smoke-validate before correctness — carried via attempt_evidence/handoff to the optimizer agent
- ins-r1d-1 (explore): re-derive from the Aug-18 32x8-lane topological-list-schedule design intent (~2139 cycles claimed, unmeasured)

## dispatch-args.json (authoritative)
- kernel_path: canonical git-HEAD perf_takehome.py (af14cbb2…, restored 2026-08-19 after Aug-18 mutation found failing correctness)
- evaluation_root: workflow-authoring/candidates (round 1 took candidate-0; exclusive creation → candidate-1)
- test_command: /Users/haiyan-infiniai/homebrew/bin/python3 tests/submission_tests.py CorrectnessTests.test_kernel_correctness
- benchmark_command: /Users/haiyan-infiniai/homebrew/bin/python3 -c "import sys; sys.path.insert(0,'tests'); from submission_tests import cycles; print('CYCLES:', cycles())"
- baseline: 147734; model_mechanical/generation: sonnet/sonnet; exp_dir: run-2
- attempt_evidence: run-1 attempt-result verbatim; attempt_plan: round-2-selection; experience_excerpts: 4 user_provided from round-1-transfer
- Provenance: resolver envelope gotcha ({workflows:[...]} wrap needed), CUDA-prefixed empty commands discarded, 4-not-5 excerpts (round-1 file authoritative)

## Gates
- inject-runtime-controls: no-op | validate-dispatch: DISPATCH READY (channel ③ attempt_plan present)
- harness-preflight: PREFLIGHT OK (WARN #46 only) | cost: ok | budget: continue

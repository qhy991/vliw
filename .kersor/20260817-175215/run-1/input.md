# Round 1 Dispatch Input (re-dispatch after proposal_runtime_defect)

## Selected workflow
- name: vliw-bundle-packing-optimization-2 (probation, authored; session-local)
- workflow.js: workflow-authoring/proposals/vliw-bundle-packing-optimization-2/workflow.js (sha256 44b194f8f17876e826f5e9d74b223858dee772a4196d3f5a128eef9bb6016e00)
- selection: round-1-selection.json committed via finalize-selection.sh (ROUTED_BY=fallback, FALLBACK_PICK after old-proposal registry repair)

## Prior failure this round
- v3 dispatch (workflow vliw-bundle-packing-optimization, pre-fix) failed: ReferenceError EVAL_DIR at Evaluate-phase prompt construction (raw_failure_code proposal_runtime_defect). Fixed by escaping ${EVAL_DIR} placeholders; renamed to -2 and re-saved. Resume replay impossible (journal script_hash mismatch), so this dispatch runs fresh.

## Canonical state (re-verified 2026-08-19)
- perf_takehome.py restored to git HEAD af14cbb2e8666aaba375aa6875e731b176875cb89b6f870473ae05cda979c15d after discovering an Aug-18 mutation (284+/183- vs HEAD) that FAILED correctness; the mutated variant is preserved at perf_takehome.py.attempt-20260818-1734, and a passing 15.03x variant (9832 cycles) sits in perf_takehome.py.bak — both OUTSIDE the canonical path.
- Correctness: PASS exit 0 (8/8, 147734 cycles). Benchmark: CYCLES: 147734 → 1.0x. baseline=147734 confirmed.

## dispatch-args.json
See dispatch-args.json (authoritative). Key values:
- kernel_path: /Users/haiyan-infiniai/Agent4Kernel/vliw-dsh-kersor-10/perf_takehome.py
- evaluation_root: <SESSION>/workflow-authoring/candidates (exists, empty)
- test_command: python3 tests/submission_tests.py CorrectnessTests.test_kernel_correctness (eval-dir-relative)
- benchmark_command: python3 -c "import sys; sys.path.insert(0,'tests'); from submission_tests import cycles; print('CYCLES:', cycles())" (unittest SpeedTests form rejected: asserts cycles < BASELINE → exit 1 at baseline parity)
- baseline: 147734
- model_mechanical/model_generation: sonnet/sonnet
- exp_dir: <SESSION>/run-1
- experience_excerpts: 5 user_provided items from round-0-transfer.json
- attempt_evidence: null (no run-0); attempt_plan: verbatim from round-1-selection.json

## Provenance
dispatch-args-provenance.json. Notable: resolver's CUDA_VISIBLE_DEVICES-prefixed truncated commands discarded — test-method.md stores commands in fenced code blocks that kf_md_field_clean cannot read; overrides carry verified full commands. OVERRIDES file (/tmp/vliw-overrides.json) was absent at synthesis; values applied from invocation ground truth and corroborated against session artifacts.

## Gates
- inject-runtime-controls: no-op (non-campaign)
- validate-dispatch: DISPATCH READY (no missing required args; harness contract satisfied)
- harness-preflight: PREFLIGHT OK (WARN #46 model-availability gate skipped — no allowlist configured)
- estimate-dispatch-cost: verdict ok (recommended_breadth 3; no breadth knob on this workflow)
- check-runtime-budget: action=continue
- mark-dispatch-start: .dispatch-in-progress @ 2026-08-19T11:20:25Z

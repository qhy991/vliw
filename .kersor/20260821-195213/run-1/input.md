# Run 1 Dispatch Input — `vliw-bundling-kernel-optimization`

## Dispatch args

Resolved by `scripts/resolve-args.sh` (auto_dispatch=true, must_ask=[]) and
synthesized per `agents/dispatch-arg-synthesizer.md` by the host rescue path:
`run-1/dispatch-args.json`

- kernel_path: /Users/haiyan-infiniai/Agent4Kernel/vliw-dsh-kersor-12/perf_takehome.py
- test_command: pinned-interpreter CorrectnessTests.test_kernel_correctness
- benchmark_command: pinned-interpreter cycles() probe (witness-equivalent)
- baseline_cycles: 147734 (baseline-witness.json, kernel sha af14cbb2…)
- target_speedup: 8

## Provenance

Per-field sources in `run-1/dispatch-args-provenance.json`.
Host amendments documented there: pinned interpreter (system python3 3.9.6
cannot parse the frozen match syntax), narrowed correctness class, assertion-free
benchmark probe.

## Resolver audit

resolver `resolve-args.sh` output: missing_required=[], must_ask=[], auto_dispatch=true.
No unmet note requirements; user_note is empty for this session.

## Gates already passed

- check-workflow-syntax.py: passed (chunked Generate rewrite)
- prepare-dsh-workflow.mjs: DSH WORKFLOW READY, compatibility verdict=pass
- harness-preflight.sh: PREFLIGHT OK (blocked=false)

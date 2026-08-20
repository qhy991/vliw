# Methodology Review — vliw-dsh-kersor-10 (session 20260817-175215)

Reviewer: the session operator (Claude), reviewing the full round-1 → round-2 loop
against `postmortem-evidence.json` / `POSTMORTEM_EVIDENCE.md`. Outcome under review:
COMPLETE at 21.4231x (147734 → 6896 cycles), correctness PASSED 8/8, target 8.0x.

The review separates three intervention events recorded in `trace.jsonl` (all round 1),
then the protocol-out-of-band changes the operator made around the loop. Each
intervention gets one dedicated paragraph with root cause, fix, and an upstream-PR
verdict.

## Intervention 1 — stock workflows all rejected (workflow_authoring, round 1)

`trace.jsonl` seq 2: "all 4 stock workflows rejected: integration_pattern
custom_simulator unsupported". **Root cause:** every stock workflow in the catalog
declares an integration pattern (`cuda`/`rocm`/`triton`-style GPU harnesses) that
assumes an ncu-visible GPU kernel; this task is a CPU-hosted VLIW bundle-packing
simulator (`frozen_problem.py` + cycle-counting `Engine`), so the stock preambles'
`integration_pattern` contract cannot be satisfied — a genuine capability gap, not a
mis-selection. **Fix:** author a session-local workflow (`vliw-bundle-packing-optimization`,
later `-2`) whose Evaluate phase runs the task's own `submission_tests.py` /
`cycles()` commands instead of GPU profiling, registered through the normal
proposal → catalog path with fail-closed acceptance (overall_speedup null on any
evidence failure). **Upstream PR:** yes, worth one — the catalog filter should skip
integration-pattern-incompatible workflows *before* selection and say so in the
selection report, instead of letting the agent discover the incompatibility by
rejecting all four in sequence. Small, contained change to selection-time filtering.

## Intervention 2 — authored v1 used fs globals absent from the AKW sandbox (dispatch_failure, round 1)

`trace.jsonl` seq 3: "authored proposal uses fs globals absent from AKW sandbox;
needs fresh authoring with agent()-shell IO". **Root cause:** the first authored
workflow read/wrote files through ambient `fs`-style globals; the AKW
(workflow-host) sandbox exposes no such globals, so the dispatch died at first
file touch — an authoring-contract violation (the workflow source referenced
capabilities the runtime never provides). **Fix:** re-author (see Intervention 3).
The dispatch itself failed cleanly with no partial artifacts; no result was
salvaged, correctly. **Upstream PR:** borderline — the deeper fix is a
authoring-time lint in the proposal validator that rejects workflow sources
referencing undeclared runtime globals, the same way it already rejects the four
nondeterminism lexemes. That check would have caught v1 before any dispatch
budget was spent. I'd file it; effort is small and the failure mode is expensive.

## Intervention 3 — re-authored v2 routes all IO through agent() shell turns (workflow_authoring, round 1)

`trace.jsonl` seq 4: "re-authored: v1 used fs globals absent from AKW sandbox; v2
routes all IO through agent() shell turns". **Root cause:** same as Intervention 2 —
the correct IO idiom for this runtime is `agent()` turns that run shell commands
(cat/heredoc/python), not in-script file APIs. **Fix:** v2 (`vliw-bundle-packing-optimization-2`,
workflow content sha256:44b194f8…) performs every read and write — candidate
emission, hash verification, test/benchmark execution, evidence capture — through
agent shell turns, and this version dispatched and completed both rounds. **Upstream
PR:** no code change needed beyond the Intervention-2 lint; the sandbox contract
itself is correct and v2 proves the agent()-shell idiom works. Documentation PR
optional (an "IO in authored workflows" section in the authoring guide would
prevent the v1 mistake).

## Protocol-out-of-band changes (operator, outside the agent loop)

These were made by the operator between rounds to keep the protocol's evidence
chain intact; none touched candidate code or measurements, and each is recorded
here because the hook asks for one paragraph per out-of-band change:

- **Proposal registry repair.** The superseded proposal dir inside
  `workflow-authoring/proposals/` carried a persisted `binding_hash` that never
  matched recomputation ("invalid evidence binding"), because an earlier patch
  updated member hashes but not the binding checksum. Fix: move the superseded
  dir out of the proposals root entirely (generate-catalog.sh scans every
  subdirectory, so in-place `.bak` dirs still fail) and standardize on the
  self-consistent `-2` artifact. Upstream PR: yes — `generate-catalog.sh` (or the
  validator) should skip dot/backup directories, and `proposals.py` should
  recompute-and-report *which* member broke the binding instead of a bare
  mismatch error.
- **Canonical kernel restore.** `perf_takehome.py` at the task root had been
  mutated on Aug 18 (284+/183− vs git HEAD) and that mutant failed correctness.
  Fix: `git restore --source=HEAD` after preserving both variants outside the
  canonical path; baseline re-verified 147734 cycles, 8/8. Upstream PR: no — this
  is task-tree hygiene, not a KerSor defect, though a session-start `sha256`
  pin of the canonical kernel would have caught it a round earlier (candidate
  for the same upstream lint PR as above).
- **Interpreter pin (became transfer item env-1).** The round-1 correctness agent's
  `/bin/zsh -lc python3` resolved to 3.9.6, which SyntaxErrors on
  `frozen_problem.py`'s `match op:` before any candidate code runs. Fix: absolute
  3.10+ interpreter in both dispatch commands from round 2 on. Upstream PR: not
  KerSor — but the resolver/synthesizer could record the interpreter's
  `python3 --version` as part of dispatch-args provenance so environment drift is
  visible in-band.
- **Stale attempt-result removal.** An Aug-18 `run-1/attempt-result.json` made
  `storage_kind == "canonical"`, so `kersor-attempt.py normalize` silently
  read-only no-op'd instead of rebuilding from `analysis.json`. Fix: move the
  stale file out and re-run normalize, which correctly rebuilt
  `failure_class=correctness_mismatch`. Upstream PR: yes — normalize should log
  loudly (or require `--force`) when it skips a rebuild because a canonical file
  exists; the current silent no-op looks identical to a successful rebuild.
- **active-session pointer repoint.** The session root's `active-session` file
  named sibling session 20260817-162353, so the stop hook would have advanced the
  wrong session. Fix: repoint to 20260817-175215 before invoking the hook.
  Upstream PR: yes — a hook invocation whose stdin `cwd` mismatches the
  active-session pointer should warn, since the failure mode is a silently
  no-op'ing hook.

## Loop-quality assessment

Round 1 failed closed exactly as designed (correctness exit 1 → `overall_speedup:
null`, benchmark not run, no winner) and its two root causes — missing import
preamble in the candidate, login-shell interpreter — were converted into transfer
items (fail-1, env-1) that round 2 demonstrably consumed: the round-2 candidate
opens with `from problem import HASH_STAGES, SCRATCH_SIZE, VLEN` and both commands
pin the absolute interpreter. The 21.42x result is hash-bound
(candidate sha256:78993c29… verified on disk), anchored to the frozen 147734
baseline, and the materialized `best-kernel/best.py` re-verified 8/8 at 6896
cycles in a clean layout. One advisory blemish stands in the trace: the round-2
`provenance_gate` recorded verdict=fail ("no dispatch witness for run-2 —
.dispatch-witness.jsonl missing") because the resumed dispatch bypassed the
witness-writing path; the run's real provenance lives in dispatch-args-provenance.json
plus the AKW journal, so the claim is supported, but the missing witness file is
the reason this postmortem exists and is the strongest argument for the
resume-path PR noted above.

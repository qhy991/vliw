# KerSor Issue Draft — merge of session 20260817-175215 interventions

> Local draft only. Do not submit automatically. Each section merges one or more
> interventions from `trace.jsonl` (see `postmortem-evidence.json` for the
> deterministic index) plus the out-of-band changes from `methodology-review.md`.

## Title (proposed)

Authoring/dispatch guardrails for custom_simulator tasks: selection-time
integration-pattern filtering, sandbox-global lint, and loud skip paths

## Affected versions / paths

- KerSor 2.3.1
- `kersor_core/proposals.py` (evidence binding check, L301-358)
- `scripts/generate-catalog.sh` (proposal dir scan)
- `scripts/kersor-attempt.py` / `kersor_core/attempt.py` (normalize,
  storage_kind L1708-1717)
- `hooks/kersor-stop-hook.sh` + `hooks/lib/kersor-session-lib.sh`
  (active-session resolution)
- AKW `runtime/workflow-host.mjs` (journal resume path; dispatch witness)

## Issue 1 — stock workflow selection discovers integration_pattern incompatibility only by rejection

**Merged from:** trace intervention seq 2 ("all 4 stock workflows rejected:
integration_pattern custom_simulator unsupported").

For a task whose `integration_pattern` is `custom_simulator`, all four stock
workflows were selected and then rejected in sequence, spending selection
budget to rediscover a static fact: their harness contracts assume
GPU/ncu-style kernels. Request: filter the catalog by declared
integration_pattern **before** selection and report the exclusion in the
selection report, so a custom_simulator session goes straight to the
authoring path. Session evidence: the authored fallback
(`vliw-bundle-packing-optimization-2`) then completed both rounds and hit
21.42x, so the path works once reached — the waste is purely in getting there.

## Issue 2 — no authoring-time lint for runtime globals the AKW sandbox does not provide

**Merged from:** trace interventions seq 3 + seq 4 (v1 dispatch_failure "uses fs
globals absent from AKW sandbox"; v2 re-authoring "routes all IO through
agent() shell turns").

An authored workflow that references ambient fs-style globals passes proposal
validation and dies only at dispatch time inside the sandbox, costing a full
dispatch attempt. The nondeterminism lint already rejects four forbidden
lexemes in workflow source; the same mechanism should reject references to
runtime globals the workflow host does not inject, or (weaker) the authoring
guide should document the agent()-shell IO idiom as the only sanctioned file
access. Session evidence: v2, identical task, identical acceptance contract,
dispatched and completed — the defect was purely the undeclared-global
idiom, and it was only discoverable by failing.

## Issue 3 — silent skip paths make out-of-band recovery look like success

**Merged from:** operator out-of-band changes (methodology-review.md),
compounded by the resume path:

1. `kersor-attempt.py normalize` is a read-only no-op when a canonical
   `attempt-result.json` already exists (`storage_kind == "canonical"`). A
   stale canonical file therefore silently suppresses rebuild from
   `analysis.json`; the no-op prints nothing distinguishable from a successful
   rebuild. Request: log loudly or require `--force`.
2. `generate-catalog.sh` scans every directory under the proposals root, so a
   `.bak`/superseded dir inside the root keeps failing the whole scan with
   "invalid evidence binding". Request: skip dot/backup dirs, and have the
   validator name the member hash that broke the binding instead of a bare
   mismatch.
3. The stop hook resolves the session via the `active-session` pointer with no
   cross-check against the invoking `cwd`; a stale pointer makes the hook
   silently advance a different session. Request: warn or refuse on mismatch.
4. The round-2 `--resume` dispatch bypassed the `.dispatch-witness.jsonl`
   writer, so the provenance gate (advisory mode) recorded
   `verdict: fail — no dispatch witness for run-2` even though the run's
   provenance is fully reconstructable from `dispatch-args-provenance.json`
   plus the AKW journal (3 turns replayed free, correctness/benchmark/verify
   run live). Request: the resume path should write the same witness, or the
   gate should accept the journal as an alternate witness.

## Non-issues (checked, no change requested)

- Fail-closed acceptance worked as specified in round 1: correctness exit 1 →
  `overall_speedup: null`, benchmark intentionally not run, no winner.
- Journal-based resume itself is sound (free replay of undamaged turns).
- The `custom_simulator` task path end-to-end (author → catalog → select →
  synthesize → dispatch → normalize → round synthesis → stop hook) completed
  with hash-bound evidence and a 21.4231x measured win.

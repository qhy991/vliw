# User Feedback — session 20260817-175215 (vliw-dsh-kersor-10)

Collected via the AskUserQuestion feedback prompt on 2026-08-20.

## Task outcome

**Complete — success.** Measured speedup 21.4231x (147734 → 6896 cycles,
deterministic), correctness PASSED 8/8, session target 8.0x exceeded by 2.68×.
Best kernel materialized at `best-kernel/best.py` (sha256 `78993c29…`),
re-verified in a clean layout.

## User's answers

- **User assessment:** success — the measured, evidence-bound win meets the
  target; round-1 failure and the advisory provenance-gate note are recorded in
  `methodology-review.md` but do not change the outcome.
- **Issue draft action:** keep local draft only (`issue_action: drafted_only`,
  `issue_target: local-draft`). `kersor-issue-draft.md` stays in the session
  directory; nothing is submitted upstream. If revisited later, the three merged
  issues are: integration_pattern pre-filtering in workflow selection, an
  authoring-time lint for runtime globals absent from the AKW sandbox, and the
  silent skip paths (normalize no-op on stale canonical attempt-result, catalog
  scan over backup dirs, active-session pointer mismatch, resume dispatch
  bypassing the witness writer).

## Machine-readable copy

`user-feedback.json` holds the hook-facing record with the same content.

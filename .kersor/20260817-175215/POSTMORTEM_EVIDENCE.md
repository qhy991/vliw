# KerSor Postmortem Evidence

This file is a deterministic evidence index for a Claude-authored
methodology review. It is not the final methodology review.

## Targets

- Claude-authored methodology review target: `/Users/haiyan-infiniai/Agent4Kernel/vliw-dsh-kersor-10/.kersor/20260817-175215/methodology-review.md`
- GitHub issue draft target: `/Users/haiyan-infiniai/Agent4Kernel/vliw-dsh-kersor-10/.kersor/20260817-175215/kersor-issue-draft.md`

## Session

| Field | Value |
|---|---|
| Source Session | `/Users/haiyan-infiniai/Agent4Kernel/vliw-dsh-kersor-10/.kersor/20260817-175215` |
| Phase | postmortem |
| Rounds | 2 |
| Target Speedup | 8.0x |
| Best Candidate Speedup | 21.423143851508122 |
| Retained Speedup | 21.423143851508122 |
| Retained Source | candidate |
| Final Decision | COMPLETE: the measured, evidence-bound win of 21.4231x (147734 -> 6896 cycles, deterministic ratio, correctness PASSED 8/8, anchored benchmark, hash-bound candidate) exceeds the session target_speedup of 8.0 by 2.68x, with best_improved=true over the 1.0x incumbent and the best kernel materialized and re-verified in a clean layout; round-1 directives were all honored, and residual headroom (ins-2, the scalar-gather bound) is optimization-beyond-target, not unmet objective — per Phase 7 the Stop hook's acceptance gate now adjudicates this decision, and a reject there would downgrade to CONTINUE as the hook's prerogative. |

## Round Signals

| Round | Workflow | Speedup | Speedup Source | Decision |
|---:|---|---:|---|---|
| 1 | `vliw-bundle-packing-optimization-2` | unknown | unknown | CONTINUE |
| 2 | `vliw-bundle-packing-optimization-2` | 21.423x | analysis.json:speedup | COMPLETE |

## Artifact States

| Path | Status | Files | Note |
|---|---|---:|---|
| `run-1/ncu-profiles` | absent | 0 | Directory was not present in the source session. |
| `run-1/variants` | absent | 0 | Directory was not present in the source session. |
| `run-1/round-logs` | absent | 0 | Directory was not present in the source session. |
| `run-1/failed-rounds` | absent | 0 | Directory was not present in the source session. |
| `run-2/ncu-profiles` | absent | 0 | Directory was not present in the source session. |
| `run-2/variants` | absent | 0 | Directory was not present in the source session. |
| `run-2/round-logs` | absent | 0 | Directory was not present in the source session. |
| `run-2/failed-rounds` | absent | 0 | Directory was not present in the source session. |
| `best-kernel` | present evidence | 1 | Directory contains evidence files. Read contents before drawing conclusions. |

## Review Guidance

- Separate KerSor loop issues from external workflow issues and task/benchmark issues.
- Treat missing normalized analysis as a KerSor pipeline issue.
- Treat empty scaffold directories as absence of evidence, not failed profiling by itself.
- Draft a GitHub issue only as a local Markdown draft; do not submit it automatically.

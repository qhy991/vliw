# Round 1 Workflow Selection

## Selected Workflow

- Name: vliw-bundling-kernel-optimization
- Score: 26
- Phase intent: optimize (seed_origin=provided_kernel)
- Decided by: fallback
- Selector: /Users/haiyan-infiniai/Agent4Kernel/KerSor/scripts/select-workflow.sh
- Catalog: /Users/haiyan-infiniai/Agent4Kernel/vliw-dsh-kersor-12/.kersor/20260821-195213/workflow-catalog.json

## Profile Features

- Language: python_reference
- Backend: python
- Integration Pattern: custom_simulator
- Operation Type: fused_op
- NCU Available: false
- Has Harness: true
- Bottleneck Hypothesis: instruction_mix
- Complexity Level: medium
- Design Space Size: medium

## Feature Log

- eligible base: +10
- optimizer role: +4
- session-local workflow variant: +1
- exact language compatibility: +4
- exact backend compatibility: +2
- required harness is available: +2
- phase_match: workflow implements requested phase 'portable_dsl': +3

## Evidence Warnings

Routing ran with degraded evidence; repair these before trusting the PRIOR_* signals.

- epsilon exploration is OFF for this session; set KERSOR_EXPLORE_EPSILON=0.2 before starting a research run to populate Tier-2 WSR data

## Handoff Context

_No prior transfer object yet._

## Candidate Scores

| Workflow | Score | Type | Topology | Category | Fidelity |
|---|---:|---|---|---|---|
| vliw-bundling-kernel-optimization | 26 | authored | pipeline | instruction_mix_rebalance | session_local_copy |

## Rejected Workflows

- None.

## Reproducibility

- Machine-readable selection: round-1-selection.json
- Filter and score are deterministic code, not LLM-only judgment.

## Routing Decision

- Committed workflow: vliw-bundling-kernel-optimization
- Decided by: fallback
- Phase intent: optimize
- Rationale: Stable non-semantic fallback; no valid constrained-model decision.

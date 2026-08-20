# Round 1 Workflow Selection

## Selected Workflow

- Name: vliw-bundle-packing-optimization-2
- Score: 23
- Phase intent: optimize (seed_origin=provided_kernel)
- Decided by: fallback
- Selector: /Users/haiyan-infiniai/Agent4Kernel/KerSor/scripts/select-workflow.sh
- Catalog: /Users/haiyan-infiniai/Agent4Kernel/vliw-dsh-kersor-10/.kersor/20260817-175215/workflow-catalog.json

## Profile Features

- Language: python_reference
- Backend: python
- Integration Pattern: custom_simulator
- Operation Type: unknown
- NCU Available: unknown
- Has Harness: unknown
- Bottleneck Hypothesis: unknown
- Complexity Level: unknown
- Design Space Size: unknown

## Feature Log

- eligible base: +10
- optimizer role: +4
- session-local workflow variant: +1
- variant can react to prior stalled/failed evidence: +2
- exact language compatibility: +4
- exact backend compatibility: +2

## Evidence Warnings

Routing ran with degraded evidence; repair these before trusting the PRIOR_* signals.

- epsilon exploration is OFF for this session; set KERSOR_EXPLORE_EPSILON=0.2 before starting a research run to populate Tier-2 WSR data

## Handoff Context

_Transfer object through round 0, mode=full. Honor the directives below._

### Do not retry (MUST NOT repeat — `check-directive-compliance.py` will flag a re-attempt)

- [hypothesized·user_provided] CUBLAS_COMPUTE_16F is broken on sm_89 for fp16; must use CUBLAS_COMPUTE_32F. (backend=cuda, gpu=RTX4090) [from r0:experience-bank]
- [hypothesized·user_provided] EVAL_BENCH_REF=false harness contract causes sol-execbench to skip reference timing, reporting speedup=0 for all candidates. The workflow interpreted this as total failure (all 6 attempts marked valid=false, reward=2, speedup=0) and declared convergence_status=stalled, masking real 1.02-1.04x speedups. (backend=cuda) — Future rounds must read per-candidate metrics.json directly (claimed_speedup field) or run with EVAL_BENCH_REF=true to get real speedups from the harness. Do not trust overall_speedup=1 as failure when EVAL_BENCH_REF=false. [from r0:experience-bank]

### Search-space constraints

- [hypothesized·user_provided] ksearch-kernel-optimization must NOT be selected again for this session (session_id=20260614-200847). All 6 dispatch attempts failed with agent_stall. No other tree-search or adaexplore workflow should be selected until the environment stall root cause is resolved. (backend=cuda) [from r0:experience-bank]

### Known bottlenecks to target (MUST attempt at least one candidate against each — the post-round directive-compliance check records when none is honored)

- [hypothesized·user_provided] ncu --set full is blocked on this host by ERR_NVGPUCTRPERM (RmProfilingAdminOnly=1, no root). All bottleneck claims relying on ncu stall metrics are unmeasured; only latency from CUDA events is available. (backend=cuda, gpu=RTX4090) — Future rounds should not rely on ncu for stall attribution; use CUDA-event latency deltas and roofline bandwidth % as the primary evidence axis. [from r0:experience-bank]
- [hypothesized·user_provided] ncu --set full is blocked on this host by ERR_NVGPUCTRPERM (RmProfilingAdminOnly=1, no root); stall attribution is unavailable. Confirmed in round 1: bottleneck inferred from op shape + roofline + CUDA-event latency deltas, not ncu stall metrics. (backend=cuda, gpu=RTX4090) — Do not rely on ncu for stall metrics on this host. Use CUDA-event latency deltas and roofline bandwidth % as the primary evidence axis. [from r0:experience-bank]

## Candidate Scores

| Workflow | Score | Type | Topology | Category | Fidelity |
|---|---:|---|---|---|---|
| vliw-bundle-packing-optimization-2 | 23 | authored | pipeline | multi_stage_refinement | registered_candidate |

## Rejected Workflows

- None.

## Reproducibility

- Machine-readable selection: round-1-selection.json
- Filter and score are deterministic code, not LLM-only judgment.

## Routing Decision

- Committed workflow: vliw-bundle-packing-optimization-2
- Decided by: fallback
- Phase intent: optimize
- Rationale: Stable non-semantic fallback; no valid constrained-model decision.

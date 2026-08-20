# Round 2 Workflow Selection

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

## Handoff Context

_Transfer object through round 1, mode=full. Honor the directives below._

### Gates and environment constraints

- [measured·runtime] The Evaluate correctness agent ran the test via `/bin/zsh -lc 'python3 tests/submission_tests.py ...'`, where login-shell PATH resolves python3 to /usr/bin/python3 3.9.6; frozen_problem.py uses `match op:` (Python 3.10+ syntax), so the recorded failure is a SyntaxError at frozen_problem.py:222 at import time — under this invocation ANY candidate, including a correct one, fails before the candidate is ever exercised. Re-run under Python 3.14 reaches the candidate and reveals the true defect (NameError: SCRATCH_SIZE at perf_takehome.py:136) (op=vliw-bundle-packing, host=darwin) — Pin the eval interpreter: the workflow's Evaluate phase must invoke both the correctness and benchmark commands with an absolute Python 3.10+ path (e.g. /Users/haiyan-infiniai/homebrew/bin/python3) or an explicit PATH prefix, never bare `python3` through a login shell, or every future candidate will be fail-closed on the frozen problem's match-statement syntax before its own code runs. [from r1:vliw-bundle-packing-optimization-2]

### Do not retry (MUST NOT repeat — `check-directive-compliance.py` will flag a re-attempt)

- [measured·correctness] Generated kernel was emitted as a bare class body starting at `class KernelBuilder:` — the module docstring and the required `from problem import (Engine, DebugInfo, SLOT_LIMITS, VLEN, N_CORES, SCRATCH_SIZE, Machine, Tree, Input, HASH_STAGES, ...)` preamble were dropped, so every problem-module symbol is undefined and build_kernel dies with NameError: SCRATCH_SIZE at perf_takehome.py:136 during the first alloc_scratch call (op=vliw-bundle-packing, kernel_language=python-simulator) — Emit the candidate as a COMPLETE file: preserve the original module docstring and the exact `from problem import (...)` preamble before `class KernelBuilder:`. Before invoking the correctness suite, smoke-validate the artifact with `python3 -c "import perf_takehome"` and a 1-round build_kernel call so a preamble omission is caught in-phase rather than burning the eval cycle. [from r1:vliw-bundle-packing-optimization-2]
- [hypothesized·user_provided] CUBLAS_COMPUTE_16F is broken on sm_89 for fp16; must use CUBLAS_COMPUTE_32F. (backend=cuda, gpu=RTX4090) [from r0:experience-bank]

### Search-space constraints

- [hypothesized·user_provided] ksearch-kernel-optimization must NOT be selected again for this session (session_id=20260614-200847). All 6 dispatch attempts failed with agent_stall. No other tree-search or adaexplore workflow should be selected until the environment stall root cause is resolved. (backend=cuda) [from r0:experience-bank]

### Known bottlenecks to target (MUST attempt at least one candidate against each — the post-round directive-compliance check records when none is honored)

- [inferred·llm_inferred] The starter kernel is fully scalar and serial — one engine slot per bundle — while the machine offers 12 alu / 6 valu / 2 load / 2 store / 1 flow slots per cycle; the irregular per-lane forest gather (vload is contiguous-address-only, no lane-extract or gather op in the ISA) blocks full vectorization, so the main cycle lever is cross-lane VLIW parallelism packed around the unavoidable scalar gather and data-dependent hash (op=vliw-bundle-packing, shape=forest_height=10, rounds=16, batch_size=256, kernel_language=python-simulator) — Give each batch lane private scratch registers and dependency-scoreboard-pack independent lanes into shared bundles (reject same-cycle producer-consumer and write-write hazards); vectorize only the contiguous index/value loads and lane-wise hash/branch arithmetic with vload/vstore/valu, keep hash constants deduplicated in scratch, and preserve debug compares as zero-cycle ordering barriers. [from r1:vliw-bundle-packing-optimization-2]
- [hypothesized·user_provided] ncu --set full is blocked on this host by ERR_NVGPUCTRPERM (RmProfilingAdminOnly=1, no root). All bottleneck claims relying on ncu stall metrics are unmeasured; only latency from CUDA events is available. (backend=cuda, gpu=RTX4090) — Future rounds should not rely on ncu for stall attribution; use CUDA-event latency deltas and roofline bandwidth % as the primary evidence axis. [from r0:experience-bank]
- [hypothesized·user_provided] ncu --set full is blocked on this host by ERR_NVGPUCTRPERM (RmProfilingAdminOnly=1, no root); stall attribution is unavailable. Confirmed in round 1: bottleneck inferred from op shape + roofline + CUDA-event latency deltas, not ncu stall metrics. (backend=cuda, gpu=RTX4090) — Do not rely on ncu for stall metrics on this host. Use CUDA-event latency deltas and roofline bandwidth % as the primary evidence axis. [from r0:experience-bank]
- [hypothesized·llm_inferred] Derived (from run-1/analysis.md Notes, not a source transfer item): the prior Aug-18 interrupted dispatch's 13,677-byte fully-vectorized 32x8-lane topological-list-schedule design (claimed ~2139 cycles design intent; that dispatch died at the workflow's EVAL_DIR ReferenceError before any eval dir existed, so the number is unmeasured) is the fastest re-derivation path for the next candidate once the import preamble is restored (op=vliw-bundle-packing, kernel_language=python-simulator) — Re-derive the next candidate from that design intent (32 lanes x 8 vector groups, topological list scheduler, requires batch_size divisible by VLEN), but treat ~2139 cycles as unverified narrative until measured; smoke-validate with a 1-round build_kernel before invoking the correctness suite. [from r1:vliw-bundle-packing-optimization-2]

## Candidate Scores

| Workflow | Score | Type | Topology | Category | Fidelity |
|---|---:|---|---|---|---|
| vliw-bundle-packing-optimization-2 | 23 | authored | pipeline | multi_stage_refinement | registered_candidate |

## Rejected Workflows

- None.

## Reproducibility

- Machine-readable selection: round-2-selection.json
- Filter and score are deterministic code, not LLM-only judgment.

## Routing Decision

- Committed workflow: vliw-bundle-packing-optimization-2
- Decided by: fallback
- Phase intent: optimize
- Rationale: Stable non-semantic fallback; no valid constrained-model decision.

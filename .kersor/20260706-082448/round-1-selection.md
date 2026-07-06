# Round 1 Workflow Selection

## Selected Workflow

- Name: vliw-d3d4-joint-anneal
- Score: 22
- Phase intent: optimize (seed_origin=provided_kernel)
- Decided by: model
- Selector: /home/qinhaiyan/KerSor/scripts/select-workflow.sh
- Catalog: /mnt/user_dir/shihaichao/qinhaiyan/vliw-v120-d3d4-joint/.kersor/20260706-082448/workflow-catalog.json

## Profile Features

- Language: python
- Backend: python
- Integration Pattern: standalone
- Operation Type: VLIW list-scheduler kernel (Python emitter + greedy scheduler)
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
- experimental session-local variant: -1

## Handoff Context

_Transfer object through round 0, mode=full. Honor the directives below._

### Do not retry (MUST NOT repeat — `check-directive-compliance.py` will flag a re-attempt)

- [hypothesized·user_provided] Single-position sweep + anchored combo search over d3 mask stalls at the 1132 local optimum. The 1120 champion needs FULL-SPACE simulated annealing (64-bit bit-flip spanning both d3 rounds). prefix-k on d3/d4 is NO-GO. (op=VLIW-scheduler, shape=fh10-r16-b256, dtype=n/a) [from r0:user-prior]

### Search-space constraints

- [hypothesized·user_provided] Hard gate: land only masks with full-32 PSPACE=1 < 1120 AND PSPACE=0 <= 1187. rot-27 oracle (0.33s) is a strict upper bound on full realized, so use it as a cheap search signal then full-confirm. Do not modify tests/. (op=VLIW-scheduler, shape=fh10-r16-b256, dtype=n/a) [from r0:user-prior]

### Proven starting point

- [hypothesized·user_provided] Shipped champion @1120: D3_GATHER_MASK={0,1,2,3,4,37,39,40,46,54,58}, D4_COLD_MASK={25,26,27,29,31,34}. Seed any joint SA from here. (op=VLIW-scheduler, shape=fh10-r16-b256, dtype=n/a) [from r0:user-prior]

### Known bottlenecks to target (MUST attempt at least one candidate against each — the post-round directive-compliance check records when none is honored)

- [hypothesized·user_provided] Joint D3_GATHER_MASK x D4_COLD_MASK is the live axis: d3-alone -4, d4-alone -18, both -32 (synergy on load engine). Search the two masks jointly, not separately. (op=VLIW-scheduler, shape=fh10-r16-b256, dtype=n/a) [from r0:user-prior]

## Candidate Scores

| Workflow | Score | Type | Topology | Category | Fidelity |
|---|---:|---|---|---|---|
| vliw-d3d4-joint-anneal | 22 | fork_variant | iterative | search | experimental_variant |

## Rejected Workflows

- ako4x-kernel-optimizer: not in workflows_filter; language mismatch: kernel=python
- argus-kernel-optimization: not in workflows_filter; language mismatch: kernel=python; backend mismatch: backend=python
- accelopt-kernel-optimization: not in workflows_filter; language mismatch: kernel=python; backend mismatch: backend=python; problem_type mismatch: derived=[python-kernel-optimization,gpu-kernel-optimization,kernel-optimization], workflow accepts=[cuda-kernel-optimization,cuda-kernel-generation]
- adaexplore-kernel-optimization: not in workflows_filter; known_broken: uses_forbidden_runtime_api: Math.random(); language mismatch: kernel=python; problem_type mismatch: derived=[python-kernel-optimization,gpu-kernel-optimization,kernel-optimization], workflow accepts=[triton-kernel-optimization,triton-kernel-generation]
- ascendc-kernel-optimization: not in workflows_filter; language mismatch: kernel=python; backend mismatch: backend=python; problem_type mismatch: derived=[python-kernel-optimization,gpu-kernel-optimization,kernel-optimization], workflow accepts=[ascend-kernel-optimization,ascend-kernel-generation]
- astra-kernel-optimization: not in workflows_filter; language mismatch: kernel=python; problem_type mismatch: derived=[python-kernel-optimization,gpu-kernel-optimization,kernel-optimization], workflow accepts=[cuda-kernel-optimization]
- automegakernel-megakernel-optimization: not in workflows_filter; language mismatch: kernel=python; backend mismatch: backend=python; problem_type mismatch: derived=[python-kernel-optimization,gpu-kernel-optimization,kernel-optimization], workflow accepts=[amk-schedule-search,megakernel-synthesis,llama-megakernel-optimization]
- cuda-agent-kernel-optimization: not in workflows_filter; language mismatch: kernel=python; backend mismatch: backend=python
- cudallm-fsr-kernel-generation: not in workflows_filter; language mismatch: kernel=python; problem_type mismatch: derived=[python-kernel-optimization,gpu-kernel-optimization,kernel-optimization], workflow accepts=[cuda-kernel-generation,cuda-kernel-optimization]
- cutlass-gemm-optimization: not in workflows_filter; language mismatch: kernel=python; backend mismatch: backend=python; problem_type mismatch: derived=[python-kernel-optimization,gpu-kernel-optimization,kernel-optimization], workflow accepts=[cutlass-gemm-optimization]
- fact-kernel-optimization: not in workflows_filter; language mismatch: kernel=python; backend mismatch: backend=python
- gpuforecasters-kernel-optimization: not in workflows_filter; known_broken: Script bug: 'meta is not defined' at runtime (reproduced on AMD-395 20260612-195934 run-4). Also reported ML-simulated speedups without compiling. Unblock after fixing the meta reference and enforcing real compile+correctness gating.; language mismatch: kernel=python; backend mismatch: backend=python
- gemmptx-gemm-optimization: not in workflows_filter; language mismatch: kernel=python; backend mismatch: backend=python; problem_type mismatch: derived=[python-kernel-optimization,gpu-kernel-optimization,kernel-optimization], workflow accepts=[gemm-ptx-optimization,cuda-gemm-ptx-optimization,gemm-instruction-optimization]
- generalist-kernel-optimization: not in workflows_filter; language mismatch: kernel=python; problem_type mismatch: derived=[python-kernel-optimization,gpu-kernel-optimization,kernel-optimization], workflow accepts=[cuda-kernel-generation,cuda-kernel-optimization,ascend-kernel-generation,ascend-kernel-optimization]
- in-place-patch-optimization: not in workflows_filter; language mismatch: kernel=python; backend mismatch: backend=python
- kda-kernel-workflow: not in workflows_filter; language mismatch: kernel=python; problem_type mismatch: derived=[python-kernel-optimization,gpu-kernel-optimization,kernel-optimization], workflow accepts=[cuda-kernel-optimization,cuda-kernel-generation,ascend-kernel-optimization,ascend-kernel-generation]
- keet-kernel-explanation: not in workflows_filter; language mismatch: kernel=python; backend mismatch: backend=python; problem_type mismatch: derived=[python-kernel-optimization,gpu-kernel-optimization,kernel-optimization], workflow accepts=[performance-explanation]
- ksearch-kernel-optimization: not in workflows_filter; known_broken: uses_forbidden_runtime_api: Date.now(); language mismatch: kernel=python
- kernelagent-triton-synthesis: not in workflows_filter; language mismatch: kernel=python; problem_type mismatch: derived=[python-kernel-optimization,gpu-kernel-optimization,kernel-optimization], workflow accepts=[triton-kernel-generation,operator-generation]
- kernelband-kernel-optimization: not in workflows_filter; language mismatch: kernel=python
- kernelblaster-kernel-optimization: not in workflows_filter; language mismatch: kernel=python; backend mismatch: backend=python; problem_type mismatch: derived=[python-kernel-optimization,gpu-kernel-optimization,kernel-optimization], workflow accepts=[cuda-kernel-optimization]
- kernelfoundry-kernel-optimization: not in workflows_filter; language mismatch: kernel=python
- kernelfoundrydx-kernel-optimization: not in workflows_filter; language mismatch: kernel=python; backend mismatch: backend=python; problem_type mismatch: derived=[python-kernel-optimization,gpu-kernel-optimization,kernel-optimization], workflow accepts=[triton-kernel-optimization,triton-kernel-generation]
- kernelskill-kernel-optimization: not in workflows_filter; language mismatch: kernel=python; problem_type mismatch: derived=[python-kernel-optimization,gpu-kernel-optimization,kernel-optimization], workflow accepts=[cuda-kernel-optimization,cuda-kernel-generation]
- llamacpp-embedded-search: not in workflows_filter; language mismatch: kernel=python; backend mismatch: backend=python
- llamacpp-metal-embedded-search: not in workflows_filter; language mismatch: kernel=python; backend mismatch: backend=python
- regrapht-kernel-optimization: not in workflows_filter; language mismatch: kernel=python; problem_type mismatch: derived=[python-kernel-optimization,gpu-kernel-optimization,kernel-optimization], workflow accepts=[cuda-kernel-optimization,kernel-search]
- stark-kernel-optimization: not in workflows_filter; known_broken: uses_forbidden_runtime_api: Math.random(); language mismatch: kernel=python; problem_type mismatch: derived=[python-kernel-optimization,gpu-kernel-optimization,kernel-optimization], workflow accepts=[cuda-kernel-optimization,kernel-search]
- stitchcuda-kernel-optimization: not in workflows_filter; language mismatch: kernel=python; problem_type mismatch: derived=[python-kernel-optimization,gpu-kernel-optimization,kernel-optimization], workflow accepts=[cuda-kernel-generation,cuda-kernel-optimization]
- tritorx-operator-generation: not in workflows_filter; language mismatch: kernel=python; backend mismatch: backend=python; problem_type mismatch: derived=[python-kernel-optimization,gpu-kernel-optimization,kernel-optimization], workflow accepts=[aten-triton-operator-generation,operator-generation]
- warpspeed-kernel-search: not in workflows_filter; language mismatch: kernel=python; backend mismatch: backend=python; problem_type mismatch: derived=[python-kernel-optimization,gpu-kernel-optimization,kernel-optimization], workflow accepts=[cuda-kernel-optimization,kernel-search]
- xe-forge-kernel-optimization: not in workflows_filter; language mismatch: kernel=python; backend mismatch: backend=python; problem_type mismatch: derived=[python-kernel-optimization,gpu-kernel-optimization,kernel-optimization], workflow accepts=[xpu-kernel-optimization,triton-kernel-optimization]
- cupilot-kernel-optimization: not in workflows_filter; language mismatch: kernel=python; backend mismatch: backend=python; problem_type mismatch: derived=[python-kernel-optimization,gpu-kernel-optimization,kernel-optimization], workflow accepts=[cuda-kernel-optimization]
- shape-specialization-kernel-optimization: not in workflows_filter; language mismatch: kernel=python; backend mismatch: backend=python
- vliw-anneal-optimizer: not in workflows_filter
- vliw-sparse-mask-search: not in workflows_filter

## Reproducibility

- Machine-readable selection: round-1-selection.json
- Filter and score are deterministic code, not LLM-only judgment.

## Routing Decision

- Committed workflow: vliw-d3d4-joint-anneal
- Decided by: model
- Phase intent: optimize
- Rationale: Round-0 transfer item fs-1 (avoid directive, evidence=user_provided) states the base single-position sweep + size-2/3 combo search over the d3 mask stalls at the 1132 local optimum, and that the 1120 champion required FULL-SPACE simulated annealing spanning both d3 rounds. The base vliw-sparse-mask-search implements exactly that stalled sweep+combo method, so re-picking the base would re-run a transfer-marked failed_strategy. The newly registered vliw-d3d4-joint-anneal variant is a fork of that base whose description replaces sweep+combo with two-phase SA (rot-27 oracle collection then full-32 confirm) that co-perturbs D3_GATHER_MASK and D4_COLD_MASK together — precisely the method fs-1 says is required, on the exact masks fs-1 says to search. bn-1 (explore directive) further specifies the live axis is the JOINT D3_GATHER_MASK x D4_COLD_MASK search with synergy on the load engine (d3-alone -4, d4-alone -18, both -32); the variant's when_to_use names this joint d3×d4 axis verbatim, and it targets the profile's load-binding bottleneck (load ~2086 / floor 1043.0 in kernel-profile.md) that the d3×d4 load-engine synergy attacks. sc-1 (constrain directive) mandates a hard dual landability gate (full-32 PSPACE=1 < best AND PSPACE=0 <= bound) and rot-27-then-full-confirm discipline; the variant's when_to_use encodes exactly this dual PSPACE gate. vw-1 (reuse directive) provides the 1120 champion masks to seed any SA from, which the variant can consume directly. No prior measured run exists (round 1, no analysis.json), no escape-consult, no plateau signal to contradict. The variant is the only eligible candidate (all 30+ other catalog entries vetoed on language=python / backend=python / problem_type, including the base vliw-sparse-mask-search which is itself vetoed as 'not in workflows_filter' this round), and it is the purpose-built method for this exact axis — the prior routing's low-confidence 'right levers, contraindicated method' caveat on the base is now resolved because the variant swaps the method to full-space joint SA while keeping the on-axis d3×d4 levers.

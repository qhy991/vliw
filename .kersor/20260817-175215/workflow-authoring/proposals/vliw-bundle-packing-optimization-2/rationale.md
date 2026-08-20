# Rationale: vliw-bundle-packing-optimization (staging-v2)

## Optimization Method

VLIW bundle packing + SIMD vectorization for a custom-VLIW Python-simulator kernel.

### Primary: VLIW Instruction Bundling
The baseline emits one slot per instruction bundle (one `{engine: [slot]}` per cycle),
achieving 147734 cycles for the standard workload. The architecture supports up to
23 functional slots per cycle (12 ALU + 2 LOAD + 2 STORE + 1 FLOW + 6 VALU), but
the baseline uses only 1 — a slot utilization of ~4%. The optimization packs
independent operations into multi-slot bundles, filling the available slot budget
per cycle. Key bundling rules followed: all effects take effect at cycle end,
inputs read before any write in the same cycle, and independent operations
without data dependencies can be parallelized.

### Secondary: SIMD Vectorization (VLEN=8)
Where the data layout is contiguous across batch elements, scalar ALU operations
are replaced with VALU SIMD vector operations processing 8 elements at once.
This includes vload/vstore for contiguous memory access, vbroadcast for
scalar-to-vector promotion, and vselect for vectorized conditional selection.

### Scratch Optimization
Pre-compute constants, reuse scratch space across iterations, and minimize
redundant loads of the same value.

### Pipeline
Overlap loads with computation across loop iterations where possible.

## Baseline
- Cycles: 147734
- Target speedup: 8.0x (target cycles: ~18467)
- Correctness: baseline PASS (exit 0, 8/8 iterations correct)
- Benchmark: 147734 cycles (speedup 1.0x)

## Critical Sandbox Constraint (infra-fix for previous attempt)

The previous attempt (staging-v1) failed with `failure_class=infra` because the
workflow.js used `readFile()`, `writeFile()`, `mkdir()`, `exec()`, and
`crypto.subtle.digest()` — globals that do not exist in the AKW VM sandbox
(`runtime/workflow-host.mjs`). The sandbox provides only `agent`, `evaluate`,
`phase`, `parallel`, `pipeline`, `log`, `budget`, `setTimeout`, `clearTimeout`,
and `process.env`.

This version routes ALL file IO through `agent()` turns. The LLM agent receives
a prompt containing shell commands (`cat`, `mkdir`, `cp`, `python3 -c`) and
executes them via its own bash tool, returning structured results through the
agent's schema. The workflow.js never calls `readFile`, `writeFile`, `mkdir`,
`exec`, or `crypto.subtle` directly. It also avoids the four forbidden
nondeterminism lexemes: `Date.now`, `new Date`, `Math.random`,
`performance.now`.

## Evaluation Flow

1. **Analyze** (agent): Read canonical kernel source, problem.py, and
   submission_tests.py via `cat` commands. Returns the source contents as
   structured fields.
2. **Bundle-And-Vectorize** (agent): Generation agent receives the full kernel
   source and emits an optimized KernelBuilder class with VLIW bundling and
   SIMD vectorization.
3. **Evaluate** (3 agent turns):
   a. Setup: Agent creates an exclusive evaluation directory (try `mkdir` with
      counter 0..99 until success), copies canonical files via `cp`, writes
      the candidate via `python3 -c` with atomic write, computes SHA-256 via
      `python3 -c "import hashlib"`.
   b. Correctness: Agent runs the test command from the eval directory, returns
      stdout, stderr, exit code, and pass/fail.
   c. Benchmark (conditional on correct): Agent runs the benchmark command,
      parses the `CYCLES: <N>` line, returns the numeric value.
4. **Report**: Compute speedup as `baseline / measured_cycles`, return
   `{ overall_speedup, best_kernel_code }` with SHA-256-bound candidate source.

## Routing Axes
- languages: `python_reference` — the kernel is a Python DSL for VLIW instructions
- backends: `python` — the custom simulator runs on Python
- integration_patterns: `custom_simulator` — the task uses a custom VLIW
  simulator harness, not a standalone compiler or GPU runtime
- technique: `vliw_bundle_packing` (proposed) — not in the canonical taxonomy;
  closest canonical is `instruction_scheduling` but VLIW bundle packing is a
  distinct multi-slot-per-cycle dispatch method
- optimization_phases: `workload_dispatch` — the optimization is a static
  instruction scheduling / bundling transformation applied at kernel-construction
  time, not a backend-native compiler pass

## Fidelity Boundary
`registered_candidate`: The workflow creates a Session-local evaluation directory
with exclusive creation, copies canonical files (problem.py, tests/) as
read-only, writes the candidate as perf_takehome.py, binds it with SHA-256,
runs the mandated test and benchmark commands, and returns the measured speedup
and best kernel code. It does not modify the canonical kernel_path.
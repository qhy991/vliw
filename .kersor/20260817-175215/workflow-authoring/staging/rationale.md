# VLIW Bundle-Packing + SIMD Vectorization Optimization

**Type:** Authored workflow (probation). First catalog entry with `topology: pipeline` and `method_category: multi_stage_refinement` for the `python_reference` / `python` / `custom_simulator` axis.

## Why this workflow, and why existing workflows cannot satisfy the task

The routing gap (`routing_gap` in `author-context.json`) shows that all 4 existing workflows were rejected with the same reason:

> `integration_pattern mismatch: input=custom_simulator (workflow cannot register into this build system)`

The existing catalog covers:
- **KSearch** (`tree_exploration`): World-model-guided tree search for GPU kernels — assumes a GPU compilation/execution environment and cannot produce or evaluate VLIW simulator instructions.
- **aiter-bpreshuffle-csv-tuning** (`config_tuning`): Registry-dispatch tuning for AITER ROCm — assumes a framework-tuning workflow with CSV configs, not a VLIW instruction stream.
- **regime-aware-fusion** (`multi_stage_refinement`): CUDA operator fusion for sol-execbench — assumes a CUDA compilation chain and harness-graded solution.json format.
- **shape-specialization** (`spec_to_kernel`): CUDA constexpr baking — assumes a CUDA compilation environment and shape-stability precondition.

None of these workflows can operate on a Python DSL that generates VLIW instruction bundles for a custom simulator. The `custom_simulator` integration pattern means the task has its own harness (`submission_tests.py` importing `perf_takehome.KernelBuilder`) and its own simulator (`problem.Machine`). The workflow must:

1. Treat the canonical source files (`perf_takehome.py`, `problem.py`, `tests/submission_tests.py`) as read-only.
2. Create a Session-local evaluation directory with exclusive creation, copy the canonical files, and write the candidate.
3. Run the task's exact `test_command` and `benchmark_command` (Python unittest commands, not GPU compilation).
4. Parse `CYCLES: <number>` from stdout to compute speedup as `baseline / cycles`.

This workflow is purpose-built for this task topology.

## Method: two-phase VLIW instruction stream optimization

### Phase 1: Bundle-And-Vectorize

The baseline kernel at `perf_takehome.py` produces 147734 VLIW instruction bundles, each containing exactly **one slot** (one `{engine: [slot]}` dict per cycle). The architecture supports up to 23 non-debug slots per cycle (12 ALU + 2 LOAD + 2 STORE + 1 FLOW + 6 VALU). The primary bottleneck is **slot utilization**: each cycle uses only 1/23 of the available slot capacity.

The generator agent receives the full canonical source, the kernel profile, and the architecture specification. It emits an optimized `KernelBuilder.build_kernel()` method that:

1. **VLIW Bundling**: Packs independent slots into the same instruction bundle using a multi-slot `build()` method. For example, instead of:
   ```python
   # Baseline: 1 slot per bundle
   self.add("alu", ("+", tmp_addr, self.scratch["inp_indices_p"], i_const))
   self.add("load", ("load", tmp_idx, tmp_addr))
   ```
   The optimized version packs them:
   ```python
   { "alu": [("+", tmp_addr, ..., ...)], "load": [("load", tmp_idx, tmp_addr)] }
   ```

2. **SIMD Vectorization**: Replaces scalar ALU operations with VALU (VLEN=8) operations where the data layout is contiguous (batch elements). Uses `vload`/`vstore` for contiguous memory access and `vbroadcast`/`vselect` for vectorized operations.

3. **Scratch Optimization**: Pre-computes constants, eliminates redundant loads, and allocates scratch space efficiently for vector operations.

### Phase 2: Evaluate (with full integrity guarantees)

The evaluation phase is the most contract-heavy part of the workflow, following the `user_note` requirements exactly:

- **Exclusive directory creation**: The evaluation directory is created under `evaluation_root` with a deterministic naming scheme (`candidate-0`, `candidate-1`, ...) using exclusive creation (`mkdir` with `recursive: false`). If the directory exists, the workflow fails rather than overwriting.
- **Canonical source isolation**: `problem.py` is copied as `problem.py`, `tests/submission_tests.py` is copied under `tests/`, and any `frozen_problem.py` is also copied. The candidate is written as `perf_takehome.py`.
- **SHA-256 binding**: The generated candidate byte buffer is hashed before writing. After persisting, the file is read back and re-hashed. The two hashes must match before any testing proceeds. `best_kernel_code` is derived from these persisted bytes, and its hash is verified to equal the same SHA-256.
- **Correctness gate**: The exact `test_command` is executed from the evaluation directory with full stdout/stderr recording. Correctness passes only when the process exits 0.
- **Benchmark gate**: The benchmark runs only after correctness passes and only when its process exits 0. The `CYCLES: <number>` line is parsed from stdout (anchored, positive integer). Speedup is computed as `BASELINE / cycles` — never from an agent report.
- **Honest abstention**: If correctness fails, the benchmark is never run. If the benchmark fails or the cycles cannot be parsed, `overall_speedup` stays `null` and `best_kernel_code` stays `null` — no fabricated or unverified values are returned.

## Metadata / contract notes

- `integration_patterns: ["custom_simulator"]` is preserved verbatim from the task's `integration_pattern` field. The existing workflows were all rejected for mismatching this pattern. This is the correct declaration for the VLIW simulator task.
- `languages: ["python_reference"]` — the kernel is written in a Python DSL that generates VLIW instruction bundles. This is not CUDA, Triton, AscendC, or any GPU-native language.
- `backends: ["python"]` — the custom simulator runs on Python (the `problem.Machine` class). No GPU or specialized-vendor backend is involved.
- `optimization_phases: ["backend_native"]` — the optimization operates directly on the VLIW instruction stream (the native instruction format of the Python simulator backend). This is not a portable DSL phase.
- `backend_portability: "explicit"` — only the `python` backend is supported. No `method_supported_backends: any` escape is used.
- `technique: "instruction_scheduling"` — canonical id in `config/technique-taxonomy.json` (`category: compute`, `aliases: ["ilp", "dual issue"]`). VLIW bundle packing is a direct application of instruction-level parallelism: the technique reorders and packs independent instructions into the same cycle to expose ILP and hide latency, which is the exact definition of `instruction_scheduling`.
- `speedup_field: "overall_speedup"` and `best_kernel_field: "best_kernel_code"` match the object literally returned by the top-level `return` statement in `workflow.js`.
- `fidelity_boundary: "registered_candidate"` — the workflow writes a candidate `perf_takehome.py` file into the evaluation directory (a Session-local copy), runs the task's own correctness/benchmark commands against it, and returns the code. The candidate is registered in the evaluation directory, not edited in-place at the canonical location.
- Every `args.*` key referenced in `workflow.js` is listed in `metadata.json`'s `all_args`. `required_args` are `kernel_path`, `evaluation_root`, `test_command`, `benchmark_command`, and `baseline` — these are essential for the workflow to function.
- No `Date.now`, `new Date`, `Math.random`, or `performance.now` is used anywhere in the workflow. The evaluation directory name uses a deterministic counter instead of a timestamp or random number.
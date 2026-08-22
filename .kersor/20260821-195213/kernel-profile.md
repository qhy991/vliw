# Kernel Profile

## Parseable Fields

- Kernel Path: /Users/haiyan-infiniai/Agent4Kernel/vliw-dsh-kersor-12/perf_takehome.py
- Language: python_reference
- Backend: python
- Optimization Phase: portable_dsl
- Integration Pattern: custom_simulator
- Kernel Path Role: standalone
- Optimizable Unit: self
- Operation Type: fused_op
- Problem Shape: forest_height=10, n_nodes=2047, batch_size=256, rounds=16
- Requires Partial Patch: false
- Requires Embedded Registration: false
- NCU Available: false
- Profiler Available: none
- TF32 Matmul Default: unknown
- TF32 cudnn Default: unknown
- float32 Matmul Precision: unknown
- GPU Model: unknown
- Has Harness: true
- Harness Path: /Users/haiyan-infiniai/Agent4Kernel/vliw-dsh-kersor-12/tests/submission_tests.py
- Bottleneck Hypothesis: instruction_mix
- Utilization (min): 4%
- Utilization (max): 65%
- Complexity Level: medium
- Design Space Size: medium
- Shape Stability: fixed
- LOC: 275

## Existing Optimizations

- None implemented. The baseline `build()` method places each slot in its own single-engine instruction bundle, producing zero VLIW parallelism and zero vectorization.
- The kernel uses only scalar `alu`, `load`, `store`, `flow`, and `debug` engines. The `valu` (vector), `vload`, and `vstore` engines are unused.
- Scratch constants are cached via `const_map` to avoid redundant `const` loads.

## Notes

- **Architecture**: The target is a custom VLIW SIMD Python simulator (not a hardware GPU). The machine has 1 core, SLOT_LIMITS = {alu: 12, valu: 6, load: 2, store: 2, flow: 1, debug: 64}, VLEN=8, SCRATCH_SIZE=1536.
- **Baseline**: 147,734 cycles (1.0× speedup). Each non-debug instruction executes in its own cycle — ~4% slot utilization out of 23 max slots/cycle.
- **Bottleneck**: `instruction_mix` — the kernel uses zero VLIW bundling and zero vectorization. The `build()` method emits one slot per instruction bundle, so only 1 of 23 available slots is used per cycle. The sequential hash chain (6 stages × 3 ALU ops each) is the critical dependency path. The gather access pattern `forest_values_p[idx]` (non-contiguous per-element loads) limits vectorization of the tree-value lookup.
- **Utilization (min) = 4%** is the baseline: 1 slot/cycle ÷ 23 max slots/cycle at 147,734 cycles.
- **Utilization (max) = 65%** is an estimate of the achievable ceiling with VLIW bundling, vectorization (VLEN=8, processing 256/8=32 vector lanes per round), and software pipelining, while accounting for the sequential hash-chain dependency and the gather bottleneck. The best-known threshold (1363 cycles from `test_opus45_improved_harness`) corresponds to ~108× speedup, consistent with aggressive VLIW+SIMD utilization.
- **Problem Shape** is fixed: forest_height=10, n_nodes=2^(10+1)−1=2047, batch_size=256, rounds=16 (the single benchmark workload in `tests/submission_tests.py`).
- **Integration Pattern** is `custom_simulator` because the performance contract is a repository-local Python VLIW interpreter, not a hardware compiler/runtime. The session config enforces `integration_pattern_contract: "custom_simulator"`. A CUDA-style standalone workflow is structurally incompatible even though the source is a single file.
- **No deployment-topology.md** exists in SESSION_DIR, so all determinations are derived from first principles.
- **Environment**: No NVIDIA, AMD, Ascend, or MetaX hardware. The target is the pure-Python simulator in `frozen_problem.py`. TF32 probes are not applicable (backend is `python`, not torch-based).
- **Harness**: The benchmark harness is `tests/submission_tests.py` (SpeedTests) which runs `do_kernel_test(10, 16, 256)` and measures cycles via the simulator's `Machine.cycle` counter. The correctness harness is `tests/submission_tests.py` (CorrectnessTests) which runs the same workload 8 times.
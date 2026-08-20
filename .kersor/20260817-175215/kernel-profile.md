# Kernel Profile: VLIW SIMD Forest Kernel

## General
- **Kernel**: `KernelBuilder.build_kernel()` in `perf_takehome.py`
- **Language**: python_reference (Python DSL that generates VLIW instructions)
- **Backend**: python (custom simulator)
- **Operation Type**: custom_vliw_kernel
- **Input**: forest_height=10, rounds=16, batch_size=256

## Kernel Characteristics
- **Instruction generation**: Builds a list of VLIW instruction bundles
- **Current strategy**: 1 slot per instruction bundle (no bundling)
- **Instruction count**: ~147734 bundles (one per cycle)
- **Scratch usage**: ~20 scratch variables (within 1536 limit)
- **Control flow**: Single loop nest (rounds × batch_size), no branches per iteration

## Bottleneck Analysis
- **Primary bottleneck**: Slot utilization — each cycle executes only 1 slot out of potentially 24+ available (12 ALU + 2 LOAD + 2 STORE + 1 FLOW + 6 VALU = 23 slots max)
- **Secondary bottleneck**: No SIMD vectorization — all operations are scalar
- **Tertiary**: No scratch reuse optimization — many redundant loads of constants

## Key Operations per Iteration
Per (round, batch_element):
- 2 LOAD (load index, load value)
- 1 LOAD (load node value from forest)
- 1 ALU XOR
- ~4×4=16 ALU ops for hash stages
- 2 ALU + 1 FLOW for modulus/even-check
- 2 ALU for next_idx computation
- 1 ALU + 1 FLOW for wrap check
- 2 STORE (store index, store value)
- ~10+ ALU/LOAD for address computation and constant loading

## Optimization Directions
1. **VLIW Bundling**: Pack multiple slots per cycle (e.g., 2 LOAD + 2 ALU + 1 STORE per cycle)
2. **SIMD Vectorization**: Use VALU to process VLEN=8 elements at once where possible
3. **Scratch optimization**: Pre-compute and reuse constants, avoid redundant loads
4. **Pipeline**: Overlap loop iterations across the round/batch structure

## Complexity Level
- **Algorithmic**: Low (simple tree traversal + hash)
- **Implementation**: Medium (custom VLIW ISA, requires understanding of slot limits)
- **Design Space**: Medium (many bundling strategies, vectorization choices)

## NCU Available
- N/A (custom simulator, not GPU)

## Has Harness
- Yes (Python unittest via `tests/submission_tests.py`)
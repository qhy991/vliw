export const meta = {
  name: 'vliw-bundling-kernel-optimization',
  description: 'VLIW instruction bundling and vectorization for a custom Python VLIW SIMD simulator: packs independent instructions into the same cycle across multiple engines (alu, valu, load, store, flow) and uses vector instructions (vload, vstore, valu) to process VLEN=8 elements per slot, targeting the custom VLIW SIMD architecture in the Anthropic performance engineering take-home.',
  whenToUse: 'When the kernel profile declares a custom VLIW SIMD Python simulator target (backend=python, language=python_reference) with instruction_mix bottleneck, zero VLIW bundling, and zero vectorization. The machine has SLOT_LIMITS = {alu:12, valu:6, load:2, store:2, flow:1, debug:64} and VLEN=8. Do NOT use for GPU kernels or real hardware backends.',
  phases: [
    { title: 'Analyze', detail: 'Read the kernel source, analyze the slot-by-slot instruction stream for bundling opportunities and vectorization candidates.' },
    { title: 'Generate', detail: 'Emit an optimized KernelBuilder.build_kernel() that packs independent instructions into VLIW bundles and uses vector engines where possible.' },
    { title: 'Report', detail: 'Return the candidate kernel source, optimization summary, and estimated speedup.' },
  ],
}

// Meta alias — the `meta` export is not in scope at runtime, so duplicate the
// literal to avoid a ReferenceError on dispatch (see validate-workflow-metadata.py).
const META = {
  name: 'vliw-bundling-kernel-optimization',
}

const WORKFLOW_NAME = META.name

// --- BEGIN inlined arg_guard ---
function __unwrapArgs(rawArgs) {
  if (rawArgs == null) return {}
  if (typeof rawArgs === 'object' && !Array.isArray(rawArgs)) return rawArgs
  if (typeof rawArgs === 'string') {
    const trimmed = rawArgs.trim()
    if (trimmed === '') return {}
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
      try {
        const parsed = JSON.parse(trimmed)
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed
        throw new Error('arg_guard: parsed JSON value is not a plain object')
      } catch (e) { throw new Error(`arg_guard: invalid JSON args: ${e.message}`) }
    }
    const out = {}
    const re = /(\w[\w.-]*)=("(?:\\\\\"|[^"])*"|\'(?:\\\\\'|[^\'])*\'|\S+)/g
    let m
    while ((m = re.exec(trimmed)) !== null) {
      let v = m[2]
      if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
        v = v.slice(1, -1)
      }
      out[m[1]] = v
    }
    if (Object.keys(out).length === 0) {
      throw new Error(`arg_guard: workflow args is a non-empty string but contains no key=value pairs and is not JSON. First 160 chars: ${trimmed.slice(0, 160)}`)
    }
    return out
  }
  throw new Error(`arg_guard: workflow args has unexpected type: ${typeof rawArgs}`)
}
// eslint-disable-next-line no-global-assign
args = __unwrapArgs(typeof args === 'undefined' ? undefined : args)
// --- END inlined arg_guard ---

args = args || {}

const KERNEL_PATH      = args.kernel_path        || ''
const TEST_CMD         = args.test_command       || ''
const BENCH_CMD        = args.benchmark_command  || TEST_CMD
const EXP_DIR          = args.exp_dir            || '/tmp/vliw_bundling_exp'
const TARGET_SPEEDUP   = parseFloat(args.target_speedup || '8')
const BASELINE_CYCLES  = parseInt(args.baseline_cycles || '147734', 10)

// =============================================================================
// Phase 1 — Analyze. Read the kernel source and identify VLIW bundling and
// vectorization opportunities. The canonical task source is read-only; the
// agent reads the source as text and returns an analysis structure.
// =============================================================================
phase('Analyze')
log(`${WORKFLOW_NAME}: analyzing kernel at ${KERNEL_PATH}`)

if (!KERNEL_PATH) {
  throw new Error(`${WORKFLOW_NAME} requires args.kernel_path pointing to the seed kernel source.`)
}

const analysis = await agent(
  `You are a VLIW SIMD kernel analyst. Read the kernel source at ${KERNEL_PATH} ` +
  `(a Python KernelBuilder class targeting a custom VLIW SIMD simulator). ` +
  `The machine has SLOT_LIMITS = {alu:12, valu:6, load:2, store:2, flow:1, debug:64}, ` +
  `VLEN=8, SCRATCH_SIZE=1536, 1 core. The baseline uses 147,734 cycles with ~4% slot ` +
  `utilization — every instruction is a single-slot bundle, so only 1 of 23 max slots ` +
  `is used per cycle. The valu, vload, vstore engines are unused. ` +
  `Identify ALL opportunities for: ` +
  `(1) VLIW bundling — which independent instructions from different engine types can ` +
  `be packed into the same instruction bundle (e.g. alu + load + flow in one cycle). ` +
  `(2) Vectorization — which loads/stores/compute can be batched using vload (VLEN=8), ` +
  `vstore, vbroadcast, and valu operations. The inner loop processes batch_size=256 ` +
  `items independently, divisible into 32 groups of 8 for vectorization. ` +
  `(3) Scratch register allocation — the current allocator allocates one name per ` +
  `slot; a VLIW-aware allocator can reuse temporaries and pre-assign for bundling. ` +
  `(4) Const cache optimization — the const_map already caches constants, but the ` +
  `scratch_const() call adds a separate const-load instruction per unique constant. ` +
  `Report the full source of the kernel's build() and build_kernel() methods, ` +
  `a per-bundle analysis of the existing instruction stream, and a concrete plan ` +
  `for the optimized build() and build_kernel() methods. ` +
  `Your final answer must be a JSON object with keys: ` +
  `"source_code" (the full build_kernel method text), ` +
  `"bundle_analysis" (a string describing each bundle opportunity), ` +
  `"vectorization_plan" (a string describing the vectorization strategy), ` +
  `"optimization_plan" (a string describing the combined VLIW+vector plan). ` +
  `Use the structured_output tool to report your final answer as a JSON object ` +
  `matching the schema exactly.`,
  { label: 'analyze-kernel', phase: 'Analyze', schema: {
      type: 'object', required: ['source_code', 'bundle_analysis', 'vectorization_plan', 'optimization_plan'],
      properties: {
        source_code: { type: 'string' },
        bundle_analysis: { type: 'string' },
        vectorization_plan: { type: 'string' },
        optimization_plan: { type: 'string' },
      },
      additionalProperties: false,
  }}
)

if (!analysis) {
  throw new Error(`${WORKFLOW_NAME}: analysis agent returned null — cannot proceed to generation.`)
}

log(`analysis: bundle_analysis.length=${analysis.bundle_analysis.length}, vectorization_plan.length=${analysis.vectorization_plan.length}`)

// =============================================================================
// Phase 2 — Generate. Emit an optimized KernelBuilder implementation with VLIW
// bundling and vectorization. The agent returns the candidate source code as
// structured data — it does NOT write files or run commands.
// =============================================================================
phase('Generate')
log(`${WORKFLOW_NAME}: generating optimized kernel`)

const candidate = await agent(
  `You are a VLIW SIMD kernel compiler expert. Based on the following analysis, ` +
  `generate a complete, optimized Python KernelBuilder class with build() and ` +
  `build_kernel() methods that implement VLIW bundling and vectorization. ` +
  `Kernel source analysis:\n\n${analysis.optimization_plan}\n\n` +
  `Bundle opportunities:\n\n${analysis.bundle_analysis}\n\n` +
  `Vectorization plan:\n\n${analysis.vectorization_plan}\n\n` +
  `The target architecture: SLOT_LIMITS = {alu:12, valu:6, load:2, store:2, flow:1, debug:64}, ` +
  `VLEN=8, SCRATCH_SIZE=1536. The baseline is 147,734 cycles. Target speedup: 8x (18,467 cycles). ` +
  `The class must be named "KernelBuilder" and be importable from "perf_takehome". ` +
  `Full API contract: KernelBuilder.__init__(), .alloc_scratch(name, length), ` +
  `.scratch_const(val), .build(slots, vliw), .add(engine, slot), .build_hash(), ` +
  `.build_kernel(forest_height, n_nodes, batch_size, rounds), .debug_info(), .instrs. ` +
  `CRITICAL RULES: ` +
  `(1) The build() method MUST pack multiple independent slots into one instruction ` +
  `bundle dict. Each instruction bundle is a dict like {engine: [slot_tuple, ...]}. ` +
  `Multiple engines can have slots in the same cycle. ` +
  `(2) Use vload/vstore/vbroadcast/valu operations for vectorization. The inner ` +
  `loop processes batch_size items; group them into batches of VLEN=8. ` +
  `(3) The hash function (build_hash) must be vectorized using valu operations. ` +
  `(4) Use vselect for the data-dependent branch in idx computation. ` +
  `(5) Pre-allocate scratch addresses for all temporaries to avoid dynamic allocation. ` +
  `(6) The debug "compare" instructions must match the reference_kernel2 trace ` +
  `for correctness checking. Each debug compare uses (round, i, "key") tuples. ` +
  `(7) The instruction stream must preserve the same pause/debug synchronization ` +
  `points as the reference kernel. ` +
  `Return ONLY the complete Python source code of the optimized KernelBuilder class ` +
  `in a single string. Use the structured_output tool to report your final answer ` +
  `as a JSON object matching the schema exactly.`,
  { label: 'generate-candidate', phase: 'Generate', schema: {
      type: 'object', required: ['kernel_code', 'summary', 'estimated_cycles'],
      properties: {
        kernel_code: { type: 'string' },
        summary: { type: 'string' },
        estimated_cycles: { type: 'number' },
      },
      additionalProperties: false,
  }}
)

if (!candidate) {
  throw new Error(`${WORKFLOW_NAME}: candidate generation agent returned null — cannot produce output.`)
}

const bestKernelCode = candidate.kernel_code || ''
const candidateSummary = candidate.summary || ''
const estimatedCycles = (typeof candidate.estimated_cycles === 'number') ? candidate.estimated_cycles : null
const estimatedSpeedup = estimatedCycles ? (BASELINE_CYCLES / estimatedCycles) : null

log(`generated: ${candidateSummary}`)
log(`estimated cycles: ${estimatedCycles}, estimated speedup: ${estimatedSpeedup}`)

// =============================================================================
// Phase 3 — Report. Return the candidate kernel code and optimization summary.
// The enclosing orchestrator installs, evaluates correctness, and benchmarks
// the candidate via test_command/benchmark_command. The workflow does NOT run
// commands or write files itself — DSH agent() children are advisory/read-only.
// =============================================================================
phase('Report')

const reportLines = [
  `${WORKFLOW_NAME}: VLIW bundling + vectorization for ${KERNEL_PATH}`,
  `---`,
  `Analysis: ${analysis.bundle_analysis.substring(0, 200)}...`,
  `Vectorization: ${analysis.vectorization_plan.substring(0, 200)}...`,
  `Candidate summary: ${candidateSummary}`,
  `Estimated cycles: ${estimatedCycles}`,
  `Estimated speedup: ${estimatedSpeedup}`,
  `---`,
  `Fidelity boundary: The candidate source is a complete KernelBuilder class.`,
  `The orchestrator must:`,
  `(1) Write the candidate to a Session-local copy of perf_takehome.py`,
  `(2) Run correctness: ${TEST_CMD || '<not provided>'}`,
  `(3) Run benchmark: ${BENCH_CMD || '<not provided>'}`,
  `(4) Compare cycles against baseline ${BASELINE_CYCLES}`,
  `The canonical task source at ${KERNEL_PATH} is read-only and never modified.`,
]
const report = reportLines.join('\n')

return {
  overall_speedup: estimatedSpeedup,
  best_kernel_code: bestKernelCode,
  candidate_summary: candidateSummary,
  estimated_cycles: estimatedCycles,
  bundle_analysis: analysis.bundle_analysis,
  vectorization_plan: analysis.vectorization_plan,
  report: report,
}
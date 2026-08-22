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

// BUDGET GUARD: a full KernelBuilder module is roughly 200-300 lines. The
// single-string kernel_code return has a hard 32k output-token ceiling per
// response, and a module plus JSON quoting can exceed it in one shot. Split
// the emission into sequential chunks that the host stitches back together:
// each chunk must be <= 120 lines and self-contained text (no commentary).
const CHUNK_SPEC = [
  { part: 1, ranges: 'module docstring, imports (only from problem: DebugInfo, HASH_STAGES, SLOT_LIMITS, VLEN, SCRATCH_SIZE; plus Python stdlib), class KernelBuilder header, __init__, debug_info, alloc/scratch helpers, const cache' },
  { part: 2, ranges: 'build(slots, vliw) — the dependence-aware multi-slot bundle packer: program-order walk, per-address last-write/last-read tracking, earliest strictly-later legal bundle, per-engine slot limits, one write per address per bundle' },
  { part: 3, ranges: 'build_hash(...) — the six-stage hash as valu ops over broadcast constant vectors; build_kernel(forest_height, n_nodes, batch_size, rounds) — the batch-SIMD main body over batch_size/VLEN vectors; final vstore; scalar tail when batch_size % VLEN != 0' },
]

function __chunkPrompt(spec) {
  return `You are a VLIW SIMD kernel compiler expert writing PART ${spec.part} of 3 of a complete, ` +
    `optimized Python KernelBuilder module. Return ONLY this part's source text. ` +
    `Part ${spec.part} covers: ${spec.ranges}. ` +
    `The parts will be concatenated verbatim in order, so: start and end at clean top-level ` +
    `boundaries for your section, do not repeat earlier parts, do not add markdown fences, ` +
    `do not add any commentary — pure Python source only, <= 120 lines. ` +
    `Context (the agreed plan — follow it exactly so the parts fit): ` +
    `SLOT_LIMITS = {alu:12, valu:6, load:2, store:2, flow:1, debug:64}, VLEN=8, SCRATCH_SIZE=1536, ` +
    `baseline 147,734 cycles from one-slot-per-bundle emission. ` +
    `Strategy: keep idx/val vectors resident in scratch (batch_size/VLEN vectors of VLEN lanes), ` +
    `gather node values with load_offset lanes, xor and run the six hash stages as valu ops over ` +
    `broadcast constant vectors (broadcast each constant once), update idx with valu mul/add plus ` +
    `vselect for the even/odd branch and the n_nodes wrap, store final vals with vstore after the ` +
    `last round only. The packer obeys end-of-cycle write visibility (consumer strictly later ` +
    `bundle), per-bundle engine slot limits, and one write per scratch address per bundle. ` +
    `Skip debug and pause slots entirely (the harness runs with enable_debug False and ` +
    `enable_pause False). Class name KernelBuilder, importable from perf_takehome. ` +
    `The kernel algorithm per batch element i, per round, in exact 32-bit wrapping arithmetic: ` +
    `node_val = mem[forest_values_p + idx]; val = myhash(val XOR node_val) using the six ` +
    `HASH_STAGES tuples from problem (tmp1 = op1(val, val1); tmp2 = op3(val, val3); ` +
    `val = op2(tmp1, tmp2)); idx = 2*idx + (1 if val even else 2); idx = 0 if idx >= n_nodes. ` +
    `After the last round store val to mem[inp_values_p + i]. Pointers forest_values_p, ` +
    `inp_indices_p, inp_values_p come from memory header words 4, 5, 6 at runtime — never hardcode. ` +
    `Import only from the frozen problem module and the Python stdlib; never import tests. ` +
    `Parametric in forest_height, n_nodes, batch_size, rounds. ` +
    (spec.part === 3
      ? `End your part with the final class-level code; the module ends here. `
      : `More parts follow yours. `) +
    `Use the structured_output tool to report your final answer as a JSON object matching ` +
    `the schema exactly.`
}

// Sequential (not parallel): each chunk is small, and order-dependent stitching
// benefits from early failure detection on part 1.
let kernelParts = []
for (const spec of CHUNK_SPEC) {
  const chunk = await agent(__chunkPrompt(spec), { label: 'generate-part-' + spec.part, phase: 'Generate', schema: {
    type: 'object', required: ['part', 'code'],
    properties: {
      part: { type: 'number' },
      code: { type: 'string' },
    },
    additionalProperties: false,
  }})
  if (!chunk || !chunk.code || !chunk.code.trim()) {
    throw new Error(`${WORKFLOW_NAME}: generate part ${spec.part} returned null or empty — cannot assemble the module.`)
  }
  log(`part ${spec.part}: ${chunk.code.split('\n').length} lines`)
  kernelParts.push(chunk.code.trimEnd())
}
const bestKernelCode = kernelParts.join('\n\n') + '\n'
const moduleLines = bestKernelCode.split('\n').length
log(`assembled module: ${moduleLines} lines`)

// Cheap static self-check on the assembled module: the harness resolves
// `from perf_takehome import KernelBuilder`, so both must be present.
if (!/class\s+KernelBuilder/.test(bestKernelCode)) {
  throw new Error(`${WORKFLOW_NAME}: assembled module lacks 'class KernelBuilder' — refusing to return a broken candidate.`)
}

const candidateSummary = `Assembled from ${CHUNK_SPEC.length} sequential structured chunks (${moduleLines} lines): ` +
  `dependence-aware VLIW bundle packing + batch-SIMD vectorization (VLEN=8) per the analyzer plan.`
const estimatedCycles = null
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
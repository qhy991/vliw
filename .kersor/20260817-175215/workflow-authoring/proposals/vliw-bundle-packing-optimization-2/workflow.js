export const meta = {
  name: 'vliw-bundle-packing-optimization-2',
  description: 'VLIW bundle-packing and SIMD vectorization workflow for a custom-VLIW Python-simulator task: packs independent scalar operations into multi-slot VLIW instruction bundles (up to 12 ALU + 2 LOAD + 2 STORE + 1 FLOW + 6 VALU per cycle), then applies SIMD vectorization (VLEN=8 VALU) where the data layout permits. Uses a Session-local candidate copy with SHA-256 binding, runs the mandated correctness and benchmark commands, and returns the speedup and best kernel code.',
  whenToUse: 'When the task is a custom-VLIW Python-simulator kernel optimization (language=python_reference, backend=python, integration_pattern=custom_simulator) whose baseline is a purely scalar, single-slot-per-cycle instruction stream and the bottleneck analysis identifies slot underutilization and missing SIMD vectorization as the primary headroom. The workflow abstains for GPU/CUDA/ROCm tasks or any task whose harness is not the VLIW simulator.',
  phases: [
    { title: 'Analyze', detail: 'Read the canonical kernel source (read-only) and the kernel profile to understand the instruction mix, slot utilization, and data-flow dependencies. Identify bundling opportunities and vectorizable loops.' },
    { title: 'Bundle-And-Vectorize', detail: 'Dispatch a generator agent to emit an optimized KernelBuilder.build_kernel() that packs multiple slots per VLIW bundle and replaces scalar ALU with VALU SIMD vector operations where the data layout is contiguous. The agent receives the full instruction trace and profile.' },
    { title: 'Evaluate', detail: 'Write the candidate into a Session-local evaluation directory (exclusive creation, SHA-256 binding, canonical problem.py/tests copied as read-only). Run the test_command and benchmark_command from that directory; verify correctness exit===0 before accepting the benchmark.' },
    { title: 'Report', detail: 'Compute speedup as baseline / measured_cycles. Return { overall_speedup, best_kernel_code } with the candidate source bound by SHA-256 provenance.' },
  ],
}

// =============================================================================
// AKW SANDBOX-CONSTRAINED WORKFLOW
// No filesystem globals (readFile/writeFile/mkdir/exec). All file IO,
// subprocess execution, and hashing is done through agent() turns that
// run shell commands. The sandbox provides: agent, evaluate, phase,
// parallel, pipeline, log, budget, setTimeout, clearTimeout, process.env.
// Deterministic only: no wall-clock or random-source APIs.
// =============================================================================

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
    const re = /(\w[\w.-]*)=("(?:\\"|[^"])*"|'(?:\\'|[^'])*'|\S+)/g
    let m
    while ((m = re.exec(trimmed)) !== null) {
      let v = m[2]
      if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) v = v.slice(1, -1)
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

// --- Required args ---
const KERNEL_PATH      = args.kernel_path || ''
const EVALUATION_ROOT  = args.evaluation_root || ''
const TEST_COMMAND     = args.test_command || ''
const BENCHMARK_COMMAND = args.benchmark_command || ''
const BASELINE         = Number(args.baseline || 147734)

// --- Optional model overrides ---
const MODEL_MECHANICAL = args.model_mechanical || 'haiku'
const MODEL_GENERATION = args.model_generation || 'sonnet'

// --- Validate required args ---
if (!KERNEL_PATH) {
  throw new Error('vliw-bundle-packing-optimization: required arg "kernel_path" is missing.')
}
if (!EVALUATION_ROOT) {
  throw new Error('vliw-bundle-packing-optimization: required arg "evaluation_root" is missing.')
}
if (!TEST_COMMAND) {
  throw new Error('vliw-bundle-packing-optimization: required arg "test_command" is missing.')
}
if (!BENCHMARK_COMMAND) {
  throw new Error('vliw-bundle-packing-optimization: required arg "benchmark_command" is missing.')
}

log(`vliw-bundle-packing-optimization: kernel_path=${KERNEL_PATH} evaluation_root=${EVALUATION_ROOT} baseline=${BASELINE}`)

// Derive the kernel directory from the kernel path (canonical source location)
const KERNEL_DIR = KERNEL_PATH.substring(0, KERNEL_PATH.lastIndexOf('/'))

// =============================================================================
// PHASE 1: Analyze
// Read the canonical kernel source and problem definition via agent() shell
// turns. All file IO goes through the LLM agent, which runs shell commands.
// =============================================================================
phase('Analyze')

const analysis = await agent(
  `You are a VLIW kernel analysis expert. Read the canonical kernel source and problem definition for a custom-VLIW Python-simulator kernel optimization task.

  The canonical kernel source is at: ${KERNEL_PATH}
  The kernel directory is: ${KERNEL_DIR}

  STEP 1: Read the kernel source by running:
  \`\`\`bash
  cat "${KERNEL_PATH}"
  \`\`\`
  Capture the FULL source content.

  STEP 2: Read the problem definition by running:
  \`\`\`bash
  cat "${KERNEL_DIR}/problem.py"
  \`\`\`
  Capture the FULL source.

  STEP 3: Read the submission tests by running:
  \`\`\`bash
  cat "${KERNEL_DIR}/tests/submission_tests.py"
  \`\`\`
  Capture the FULL source.

  STEP 4: Read the frozen problem by running:
  \`\`\`bash
  cat "${KERNEL_DIR}/tests/frozen_problem.py"
  \`\`\`
  Capture the FULL source.

  STEP 5: Brief analysis — what is the instruction mix? What bundling opportunities exist? What vectorization opportunities exist?

  Return the file contents and a short analysis.`,
  {
    model: MODEL_MECHANICAL,
    label: 'read-kernel-source',
    phase: 'Analyze',
    schema: {
      type: 'object',
      properties: {
        kernel_source: { type: 'string' },
        problem_source: { type: 'string' },
        test_source: { type: 'string' },
        frozen_problem_source: { type: 'string' },
        analysis: { type: 'string' },
      },
      required: ['kernel_source', 'problem_source', 'test_source'],
    },
  },
)

const baselineSource = analysis.kernel_source || ''
const problemSource = analysis.problem_source || ''
const testSource = analysis.test_source || ''
const frozenProblemSource = analysis.frozen_problem_source || ''

log(`Read canonical kernel source (${baselineSource.length} bytes) from ${KERNEL_PATH}`)
log(`Read problem.py (${problemSource.length} bytes)`)
log(`Read tests/submission_tests.py (${testSource.length} bytes)`)

// Retain the source for file operations in Evaluate phase
// They are stored in closure variables, not written to disk.

// =============================================================================
// PHASE 2: Bundle-And-Vectorize
// Dispatch a generator agent that emits an optimized KernelBuilder class.
// The agent analyzes the baseline and emits optimized Python code.
// =============================================================================
phase('Bundle-And-Vectorize')

const WORKFLOW_NAME = 'vliw-bundle-packing-optimization'
const KV_ENGINE_INFO = [
  'alu: 12 slots (scalar arithmetic/logic)',
  'valu: 6 slots (SIMD vector operations, VLEN=8)',
  'load: 2 slots (memory load, const, vload)',
  'store: 2 slots (memory store, vstore)',
  'flow: 1 slot (control flow: select, jump, pause, halt)',
  'debug: 64 slots (ignored by submission simulator, only for correctness checking)',
].join('\n')

const optimized = await agent(
  `You are a VLIW kernel optimization specialist. The task is a custom VLIW SIMD architecture with these engine slot limits per cycle:
${KV_ENGINE_INFO}

The baseline kernel uses only 1 slot per instruction bundle (one {engine: [slot]} per cycle), achieving 147734 cycles for forest_height=10, rounds=16, batch_size=256.

The canonical kernel source is at: ${KERNEL_PATH}
The baseline was read and is ${baselineSource.length} bytes.

The KernelBuilder class has these methods available:
- build(slots, vliw=False): packs slots into instruction bundles. Currently places one slot per bundle.
- add(engine, slot): appends a single-slot bundle.
- alloc_scratch(name, length): allocates scratch space.
- scratch_const(val): loads a constant into scratch (with dedup).
- build_hash(val_hash_addr, tmp1, tmp2, round, i): builds hash stages into a slot list.

The body of build_kernel() processes rounds x batch_size iterations, each doing:
1. Load index and value from input arrays
2. Load node value from forest
3. XOR hash (val ^ node_val) + 6 hash stages
4. Even/odd check and next-index computation
5. Wrap check (idx >= n_nodes ? 0 : idx)
6. Store updated index and value

Here is the COMPLETE baseline kernel source for reference:
\`\`\`python
${baselineSource}
\`\`\`

INSTRUCTIONS:
Generate an optimized version of KernelBuilder.build_kernel() that applies these optimizations:

### 1. VLIW BUNDLING (Primary)
Replace the single-slot-per-cycle approach with multi-slot bundling. The build() method currently does:
  for engine, slot in slots: instrs.append({engine: [slot]})
Change it to pack independent slots into the same bundle:
  { "alu": [slot1, slot2, ...], "load": [slot1, ...], "store": [slot1, ...], "flow": [slot1] }

Key bundling rules:
- All slots in the same engine execute in the same cycle (same effects timing)
- All effects (scratch writes, memory writes) take effect at the END of the cycle
- Inputs are read before any write in the cycle
- Independent operations that don't read each other's results can be packed
- Constants (load/const) can be loaded in parallel with other operations
- Loads and ALU operations that don't share dependencies can be parallelized

### 2. SIMD VECTORIZATION (Secondary)
Where the data layout is contiguous (batch elements), use VALU (VLEN=8) instead of scalar ALU:
- Replace scalar ALU loops with valu operations processing 8 elements at once
- Use vload/vstore for contiguous memory access
- Use vbroadcast to broadcast scalars to vectors
- Use vselect for vectorized conditional selection

### 3. SCRATCH OPTIMIZATION
- Pre-compute constants and reuse them
- Minimize redundant loads of the same value
- Allocate scratch intelligently for vector operations

### 4. LOOP-LEVEL OPTIMIZATION
- The inner loop iterates over batch_size elements. Consider unrolling or vectorizing.
- The outer loop iterates over rounds. The hash is data-dependent so rounds cannot be parallelized, but batch elements within a round can be.

Return the COMPLETE optimized KernelBuilder class (with build_kernel and build methods) as a Python code block. The KernelBuilder class must have the same interface so submission_tests.py can import it. The build() method must be the primary bundling mechanism.`,
  {
    model: MODEL_GENERATION,
    label: 'vliw-optimizer',
    phase: 'Bundle-And-Vectorize',
    schema: {
      type: 'object',
      required: ['kernel_code'],
      properties: {
        kernel_code: { type: 'string' },
        summary: { type: 'string' },
        bundling_strategy: { type: 'string' },
        vectorization_notes: { type: 'string' },
      },
      additionalProperties: false,
    },
  },
)

const candidateSource = optimized.kernel_code || ''
const optimizeSummary = optimized.summary || ''
const bundlingStrategy = optimized.bundling_strategy || ''
const vectorizationNotes = optimized.vectorization_notes || ''

log(`Generated optimized kernel (${candidateSource.length} bytes)`)
if (optimizeSummary) log(`summary: ${optimizeSummary}`)
if (bundlingStrategy) log(`bundling: ${bundlingStrategy}`)
if (vectorizationNotes) log(`vectorization: ${vectorizationNotes}`)

if (!candidateSource) {
  throw new Error(`${WORKFLOW_NAME}: agent returned empty kernel_code — cannot proceed`)
}

// =============================================================================
// PHASE 3: Evaluate
// Write the candidate into a Session-local evaluation directory with exclusive
// creation, SHA-256 binding, and run correctness + benchmark.
//
// All file IO is done through agent() turns that run shell commands.
// The agent() LLM executes bash commands and returns structured results.
// =============================================================================
phase('Evaluate')

// --- Step 3a: Create exclusive evaluation directory and write candidate ---
// The agent will try mkdir with a counter until it succeeds (exclusive creation).
// Then it copies canonical files and writes the candidate, computes SHA-256.
const dirSetup = await agent(
  `You are setting up an evaluation directory for a VLIW kernel candidate. All operations must be done via shell commands.

  The evaluation root is: ${EVALUATION_ROOT}
  The kernel directory (canonical source location) is: ${KERNEL_DIR}

  STEP 1: Create an exclusive evaluation directory.
  Try mkdir with a counter starting at 0, going up to 99:
  \`\`\`bash
  mkdir "${EVALUATION_ROOT}/candidate-0"
  \`\`\`
  If the exit code is 0, use candidate-0. If the exit code is non-zero (directory already exists), try candidate-1, then candidate-2, etc.
  Stop at the first success. Report the successful directory name.
  If none succeed up to candidate-99, report failure.

  STEP 2: Copy canonical files into the evaluation directory.
  Let EVAL_DIR be the successful path from step 1.
  \`\`\`bash
  cp "${KERNEL_DIR}/problem.py" "\${EVAL_DIR}/problem.py"
  mkdir -p "\${EVAL_DIR}/tests"
  cp "${KERNEL_DIR}/tests/submission_tests.py" "\${EVAL_DIR}/tests/submission_tests.py"
  cp "${KERNEL_DIR}/tests/frozen_problem.py" "\${EVAL_DIR}/tests/frozen_problem.py"
  \`\`\`
  Verify each file exists after copy:
  \`\`\`bash
  ls -la "\${EVAL_DIR}/problem.py" "\${EVAL_DIR}/tests/submission_tests.py" "\${EVAL_DIR}/tests/frozen_problem.py"
  \`\`\`

  STEP 3: Write the candidate kernel as perf_takehome.py.
  Use a Python one-liner to write the file atomically (write to .tmp then os.replace):
  \`\`\`bash
  python3 -c "
_os = __import__('os'); hashlib = __import__('hashlib')
content = '''${candidateSource.replace(/'/g, "\\'").replace(/\\n/g, "\\n")}'''
path = '\${EVAL_DIR}/perf_takehome.py'
tmp = path + '.tmp.' + str(_os.getpid())
with open(tmp, 'w') as f:
    f.write(content)
_os.replace(tmp, path)
h = hashlib.sha256(content.encode()).hexdigest()
print('SHA256:', h)
"
  \`\`\`

  STEP 4: Verify the written file by reading it back and computing SHA-256:
  \`\`\`bash
  python3 -c "
from hashlib import sha256 as _sha256
h = _sha256(open('\${EVAL_DIR}/perf_takehome.py', 'rb').read()).hexdigest()
print('SHA256:', h)
"
  \`\`\`

  Return the evaluation directory path, a list of files copied, and the SHA-256 hash.`,
  {
    model: MODEL_MECHANICAL,
    label: 'setup-eval-dir',
    phase: 'Evaluate',
    schema: {
      type: 'object',
      properties: {
        eval_dir: { type: 'string' },
        created: { type: 'boolean' },
        sha256: { type: 'string' },
        files_copied: { type: 'array', items: { type: 'string' } },
      },
      required: ['eval_dir', 'created', 'sha256'],
    },
  },
)

if (!dirSetup.created) {
  throw new Error(`${WORKFLOW_NAME}: failed to create exclusive evaluation directory under ${EVALUATION_ROOT} after 100 attempts`)
}

const evalDir = dirSetup.eval_dir
const candidateHash = dirSetup.sha256

log(`${WORKFLOW_NAME}: created exclusive evaluation directory: ${evalDir}`)
log(`${WORKFLOW_NAME}: candidate SHA-256 (pre-write) = ${candidateHash}`)

// --- Step 3b: Run correctness test ---
// The agent runs the test command from the evaluation directory and returns
// structured output including stdout, stderr, and exit code.
const correctness = await agent(
  `You are a kernel evaluation expert. Run the correctness test for the candidate kernel.

  Evaluation directory: ${evalDir}
  Test command: ${TEST_COMMAND}

  STEP 1: Run the test command from the evaluation directory:
  \`\`\`bash
  cd "${evalDir}" && ${TEST_COMMAND}
  \`\`\`
  Capture the full stdout, stderr, and exit code.

  Report the exit code and whether the test passed (exit 0 = pass).`,
  {
    model: MODEL_MECHANICAL,
    label: 'correctness-test',
    phase: 'Evaluate',
    schema: {
      type: 'object',
      properties: {
        stdout: { type: 'string' },
        stderr: { type: 'string' },
        exit_code: { type: 'number' },
        passed: { type: 'boolean' },
        summary: { type: 'string' },
      },
      required: ['stdout', 'stderr', 'exit_code', 'passed'],
    },
  },
)

log(`${WORKFLOW_NAME}: correctness stdout (first 500 chars): ${(correctness.stdout || '').substring(0, 500)}`)
if (correctness.stderr) {
  log(`${WORKFLOW_NAME}: correctness stderr (first 500 chars): ${correctness.stderr.substring(0, 500)}`)
}
log(`${WORKFLOW_NAME}: correctness exitCode: ${correctness.exit_code}, passed: ${correctness.passed}`)

let measuredCycles = null
let overallSpeedup = null
let bestKernelCode = null

// --- Step 3c: Run benchmark (only if correctness passes) ---
if (correctness.passed) {
  log(`${WORKFLOW_NAME}: correctness PASSED — running benchmark`)

  const benchmark = await agent(
    `You are a kernel evaluation expert. Run the benchmark for the candidate kernel.

    Evaluation directory: ${evalDir}
    Benchmark command: ${BENCHMARK_COMMAND}

    STEP 1: Run the benchmark command from the evaluation directory:
    \`\`\`bash
    cd "${evalDir}" && ${BENCHMARK_COMMAND}
    \`\`\`
    Capture the full stdout, stderr, and exit code.

    STEP 2: Parse the output for the CYCLES value.
    The format is: "CYCLES: <number>"
    Extract the first positive integer after "CYCLES:".
    If the output contains "CYCLES: 147734" then cycles=147734.

    Return the parsed cycles value and whether it was found.`,
    {
      model: MODEL_MECHANICAL,
      label: 'benchmark',
      phase: 'Evaluate',
      schema: {
        type: 'object',
        properties: {
          stdout: { type: 'string' },
          stderr: { type: 'string' },
          exit_code: { type: 'number' },
          cycles: { type: 'number' },
          cycles_found: { type: 'boolean' },
        },
        required: ['stdout', 'stderr', 'exit_code', 'cycles', 'cycles_found'],
      },
    },
  )

  log(`${WORKFLOW_NAME}: benchmark stdout (first 500 chars): ${(benchmark.stdout || '').substring(0, 500)}`)
  if (benchmark.stderr) {
    log(`${WORKFLOW_NAME}: benchmark stderr (first 500 chars): ${benchmark.stderr.substring(0, 500)}`)
  }
  log(`${WORKFLOW_NAME}: benchmark exitCode: ${benchmark.exit_code}`)

  if (benchmark.exit_code === 0 && benchmark.cycles_found && benchmark.cycles > 0) {
    measuredCycles = benchmark.cycles
    overallSpeedup = BASELINE / measuredCycles
    log(`${WORKFLOW_NAME}: measured ${measuredCycles} cycles, speedup=${overallSpeedup.toFixed(4)}x`)
  } else {
    log(`${WORKFLOW_NAME}: benchmark failed or no cycles found (exit=${benchmark.exit_code}, cycles_found=${benchmark.cycles_found}, cycles=${benchmark.cycles})`)
  }
} else {
  log(`${WORKFLOW_NAME}: correctness FAILED (exit ${correctness.exit_code}); not running benchmark`)
}

// --- Step 3d: Read back candidate source for return ---
// Only read back if correctness passed (no need to read if we won't return it)
if (correctness.passed) {
  const readBack = await agent(
    `Read back the candidate kernel source from the evaluation directory and verify its SHA-256 integrity.

    Evaluation directory: ${evalDir}
    Expected SHA-256: ${candidateHash}

    STEP 1: Read the candidate file:
    \`\`\`bash
    cat "${evalDir}/perf_takehome.py"
    \`\`\`
    Capture the FULL source content.

    STEP 2: Compute SHA-256 of the file on disk:
    \`\`\`bash
    python3 -c "import hashlib; h=hashlib.sha256(open('${evalDir}/perf_takehome.py','rb').read()).hexdigest(); print('SHA256:', h)"
    \`\`\`

    Compare the computed hash with the expected hash. They must match.
    Return the source content and whether the hash matches.`,
    {
      model: MODEL_MECHANICAL,
      label: 'verify-candidate',
      phase: 'Evaluate',
      schema: {
        type: 'object',
        properties: {
          source: { type: 'string' },
          hash: { type: 'string' },
          hash_matches: { type: 'boolean' },
        },
        required: ['source', 'hash', 'hash_matches'],
      },
    },
  )

  if (readBack.hash_matches && readBack.source) {
    bestKernelCode = readBack.source
    log(`${WORKFLOW_NAME}: SHA-256 binding verified: ${candidateHash}`)
  } else {
    log(`${WORKFLOW_NAME}: SHA-256 MISMATCH — expected ${candidateHash}, got ${readBack.hash || 'none'}. Using generation source as fallback.`)
    // Fallback: use the source from the generation phase
    bestKernelCode = candidateSource
  }
} else {
  // Correctness failed — still derive best_kernel_code from generation source
  // for diagnostic purposes, but speedup remains null
  bestKernelCode = candidateSource
}

// =============================================================================
// PHASE 4: Report
// =============================================================================
phase('Report')

const reportLines = []
reportLines.push(`${WORKFLOW_NAME}: VLIW bundle-packing + SIMD vectorization optimization`)
reportLines.push(`Baseline: ${BASELINE} cycles`)
reportLines.push(`Correctness: ${correctness.passed ? 'PASSED' : 'FAILED (exit ' + correctness.exit_code + ')'}`)
if (measuredCycles !== null) {
  reportLines.push(`Measured cycles: ${measuredCycles}`)
  reportLines.push(`Speedup: ${overallSpeedup.toFixed(4)}x`)
}
reportLines.push(`Evaluation directory: ${evalDir}`)
reportLines.push(`Candidate SHA-256: ${candidateHash}`)
if (optimizeSummary) reportLines.push(`Optimization summary: ${optimizeSummary}`)
if (bundlingStrategy) reportLines.push(`Bundling strategy: ${bundlingStrategy}`)
if (vectorizationNotes) reportLines.push(`Vectorization notes: ${vectorizationNotes}`)

const report = reportLines.join('\n')
log(report)

return {
  overall_speedup: overallSpeedup,
  best_kernel_code: bestKernelCode,
  candidate_hash: candidateHash,
  evaluation_dir: evalDir,
  report: report,
}
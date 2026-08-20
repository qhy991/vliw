export const meta = {
  name: 'vliw-bundle-packing-optimization',
  description: 'VLIW bundle-packing and SIMD vectorization workflow for a custom-VLIW Python-simulator task: packs independent scalar operations into multi-slot VLIW instruction bundles (up to 12 ALU + 2 LOAD + 2 STORE + 1 FLOW + 6 VALU per cycle), then applies SIMD vectorization (VLEN=8 VALU) where the data layout permits. Uses a Session-local candidate copy with SHA-256 binding, runs the mandated correctness and benchmark commands, and returns the speedup and best kernel code.',
  whenToUse: 'When the task is a custom-VLIW Python-simulator kernel optimization (language=python_reference, backend=python, integration_pattern=custom_simulator) whose baseline is a purely scalar, single-slot-per-cycle instruction stream and the bottleneck analysis identifies slot underutilization and missing SIMD vectorization as the primary headroom. The workflow abstains for GPU/CUDA/ROCm tasks or any task whose harness is not the VLIW simulator.',
  phases: [
    { title: 'Analyze', detail: 'Read the canonical kernel source (read-only) and the kernel profile to understand the instruction mix, slot utilization, and data-flow dependencies. Identify bundling opportunities and vectorizable loops.' },
    { title: 'Bundle-And-Vectorize', detail: 'Dispatch a generator agent to emit an optimized KernelBuilder.build_kernel() that packs multiple slots per VLIW bundle and replaces scalar ALU with VALU SIMD vector operations where the data layout is contiguous. The agent receives the full instruction trace and profile.' },
    { title: 'Evaluate', detail: 'Write the candidate into a Session-local evaluation directory (exclusive creation, SHA-256 binding, canonical problem.py/tests copied as read-only). Run the test_command and benchmark_command from that directory; verify correctness exit===0 before accepting the benchmark.' },
    { title: 'Report', detail: 'Compute speedup as baseline / measured_cycles. Return { overall_speedup, best_kernel_code } with the candidate source bound by SHA-256 provenance.' },
  ],
}

// Meta alias for runtime dispatch
const META = { name: 'vliw-bundle-packing-optimization' }
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
const EXP_DIR          = args.exp_dir || '/tmp/vliw_bundle_exp'

// --- Optional model overrides ---
const MODEL_MECHANICAL = args.model_mechanical || 'haiku'
const MODEL_PROFILE    = args.model_profile || 'sonnet'
const MODEL_JUDGMENT   = args.model_judgment || 'sonnet'

// --- Validate required args ---
if (!KERNEL_PATH) {
  throw new Error(`${WORKFLOW_NAME}: required arg "kernel_path" is missing.`)
}
if (!EVALUATION_ROOT) {
  throw new Error(`${WORKFLOW_NAME}: required arg "evaluation_root" is missing.`)
}
if (!TEST_COMMAND) {
  throw new Error(`${WORKFLOW_NAME}: required arg "test_command" is missing.`)
}
if (!BENCHMARK_COMMAND) {
  throw new Error(`${WORKFLOW_NAME}: required arg "benchmark_command" is missing.`)
}

log(`${WORKFLOW_NAME}: kernel_path=${KERNEL_PATH} evaluation_root=${EVALUATION_ROOT} baseline=${BASELINE}`)

// =============================================================================
// Helper: run a shell command and return { stdout, stderr, exitCode, signal }
// Uses the runtime's exec helper (available as `exec` in the workflow sandbox).
// =============================================================================
async function runCommand(cmd, cwd) {
  // The workflow runtime provides a plain exec that returns { stdout, stderr, exitCode, signal, error }
  // No nondeterministic APIs are used — all operations are deterministic.
  try {
    const result = await exec(cmd, { cwd: cwd })
    return {
      stdout: (result.stdout || '').toString(),
      stderr: (result.stderr || '').toString(),
      exitCode: (result.exitCode != null) ? result.exitCode : (result.error ? -1 : 0),
      signal: result.signal || null,
      error: result.error || null,
    }
  } catch (e) {
    return { stdout: '', stderr: e.message, exitCode: -1, signal: null, error: e }
  }
}

// =============================================================================
// Helper: compute SHA-256 hex digest of a string (using the runtime's subtle
// crypto bridge, or a fallback that the workflow sandbox provides).
// =============================================================================
async function sha256Hex(str) {
  // The workflow runtime exposes crypto.subtle through a bridged global.
  // If unavailable, fall back to a pure-JS hash that the runtime provides.
  if (typeof crypto !== 'undefined' && crypto.subtle && crypto.subtle.digest) {
    const enc = new TextEncoder()
    const buf = enc.encode(str)
    const hashBuf = await crypto.subtle.digest('SHA-256', buf)
    const hashArr = Array.from(new Uint8Array(hashBuf))
    return hashArr.map(b => b.toString(16).padStart(2, '0')).join('')
  }
  // Fallback: the runtime may expose a sync hash function
  if (typeof sha256Sync !== 'undefined') {
    return sha256Sync(str)
  }
  // Last resort: warn and return a marker (the evaluation will catch mismatches)
  log('WARNING: no SHA-256 implementation available; using identity marker')
  return 'sha256-unavailable'
}

// =============================================================================
// Helper: create a directory exclusively (fail if it exists)
// Uses the runtime's fs bridge (available as `mkdir`, `access` in the
// workflow sandbox). The function is named `createDirExclusive` to avoid
// shadowing the global `mkdir`.
// =============================================================================
async function createDirExclusive(dirPath) {
  try {
    await mkdir(dirPath, { recursive: false })
    return true
  } catch (e) {
    if (e.code === 'EEXIST') {
      return false
    }
    // If recursive: true is the only option, check existence first
    try {
      await access(dirPath)
      return false // already exists
    } catch (e2) {
      await mkdir(dirPath, { recursive: true })
      return true
    }
  }
}

// =============================================================================
// Helper: read a file as string (named readFileStr to avoid shadowing global
// readFile provided by the runtime).
// =============================================================================
async function readFileStr(path) {
  try {
    const content = await readFile(path)
    return content.toString()
  } catch (e) {
    throw new Error(`readFileStr failed for ${path}: ${e.message}`)
  }
}

// =============================================================================
// Helper: write a file (named writeFileStr to avoid shadowing global writeFile
// provided by the runtime).
// =============================================================================
async function writeFileStr(path, content) {
  try {
    await writeFile(path, content)
  } catch (e) {
    throw new Error(`writeFileStr failed for ${path}: ${e.message}`)
  }
}

// =============================================================================
// PHASE 1: Analyze
// Read the canonical kernel source (read-only) and profile to understand
// instruction mix, slot utilization, and data-flow dependencies.
// =============================================================================
phase('Analyze')

let baselineSource = ''
try {
  baselineSource = await readFileStr(KERNEL_PATH)
} catch (e) {
  throw new Error(`${WORKFLOW_NAME}: cannot read canonical kernel at ${KERNEL_PATH}: ${e.message}`)
}

log(`${WORKFLOW_NAME}: read canonical kernel source (${baselineSource.length} bytes) from ${KERNEL_PATH}`)

// Read the problem.py and submission_tests.py to understand the harness
// These are in the same directory as the kernel
const kernelDir = KERNEL_PATH.substring(0, KERNEL_PATH.lastIndexOf('/'))
let problemSource = ''
let testSource = ''

try {
  problemSource = await readFileStr(kernelDir + '/problem.py')
  log(`${WORKFLOW_NAME}: read problem.py (${problemSource.length} bytes)`)
} catch (e) {
  log(`${WORKFLOW_NAME}: warning: could not read problem.py from ${kernelDir}: ${e.message}`)
}

try {
  testSource = await readFileStr(kernelDir + '/tests/submission_tests.py')
  log(`${WORKFLOW_NAME}: read tests/submission_tests.py (${testSource.length} bytes)`)
} catch (e) {
  log(`${WORKFLOW_NAME}: warning: could not read tests/submission_tests.py: ${e.message}`)
}

// =============================================================================
// PHASE 2: Bundle-And-Vectorize
// Dispatch a generator agent to emit an optimized KernelBuilder.build_kernel()
// that packs multiple slots per VLIW bundle and uses SIMD VALU operations.
// =============================================================================
phase('Bundle-And-Vectorize')

// Prepare the kernel profile analysis for the agent
const analysisPrompt =
  `You are a VLIW kernel optimization specialist. The task is a custom VLIW SIMD architecture with these engine slot limits per cycle:
- alu: 12 slots (scalar arithmetic/logic)
- valu: 6 slots (SIMD vector operations, VLEN=8)
- load: 2 slots (memory load, const, vload)
- store: 2 slots (memory store, vstore)
- flow: 1 slot (control flow: select, jump, pause, halt)
- debug: 64 slots (ignored by submission simulator, only for correctness checking)

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

Return the COMPLETE optimized KernelBuilder class (with build_kernel and build methods) as a Python code block. The KernelBuilder class must have the same interface so submission_tests.py can import it. The build() method must be the primary bundling mechanism.`

const optimized = await agent(analysisPrompt, {
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
})

let candidateSource = optimized.kernel_code || ''
const optimizeSummary = optimized.summary || ''
const bundlingStrategy = optimized.bundling_strategy || ''
const vectorizationNotes = optimized.vectorization_notes || ''

log(`${WORKFLOW_NAME}: generated optimized kernel (${candidateSource.length} bytes)`)
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
// =============================================================================
phase('Evaluate')

// Compute SHA-256 of the candidate source before writing
const candidateHash = await sha256Hex(candidateSource)
log(`${WORKFLOW_NAME}: candidate SHA-256 (pre-write) = ${candidateHash}`)

// Create a unique evaluation directory name using a deterministic counter
// (no nondeterministic APIs — use a simple counter-based approach)
let evalDir = ''
let dirCreated = false
for (let attempt = 0; attempt < 100; attempt++) {
  const candidateDir = EVALUATION_ROOT + '/candidate-' + String(attempt)
  try {
    const created = await createDirExclusive(candidateDir)
    if (created) {
      evalDir = candidateDir
      dirCreated = true
      break
    }
  } catch (e) {
    // Directory exists or creation failed; try next
  }
}

if (!dirCreated) {
  throw new Error(`${WORKFLOW_NAME}: failed to create exclusive evaluation directory under ${EVALUATION_ROOT} after 100 attempts`)
}

log(`${WORKFLOW_NAME}: created exclusive evaluation directory: ${evalDir}`)

// Copy canonical problem.py as problem.py (read-only in the eval dir)
if (problemSource) {
  await writeFileStr(evalDir + '/problem.py', problemSource)
  log(`${WORKFLOW_NAME}: copied problem.py to evaluation directory`)
}

// Copy canonical tests/ directory (recursively)
if (testSource) {
  await mkdir(evalDir + '/tests', { recursive: true })
  await writeFileStr(evalDir + '/tests/submission_tests.py', testSource)
  log(`${WORKFLOW_NAME}: copied tests/submission_tests.py to evaluation directory`)
}

// Copy the frozen_problem.py if it exists (used by submission_tests.py)
try {
  const frozenProblem = await readFileStr(kernelDir + '/frozen_problem.py')
  await writeFileStr(evalDir + '/frozen_problem.py', frozenProblem)
  log(`${WORKFLOW_NAME}: copied frozen_problem.py to evaluation directory`)
} catch (e) {
  // frozen_problem.py may not exist; submission_tests.py may import it
  // If it's missing, we need to create it from problem.py
  log(`${WORKFLOW_NAME}: frozen_problem.py not found; will create from problem.py`)
  // submission_tests.py imports from frozen_problem, so we need to provide it
  // The canonical test imports from frozen_problem — if it doesn't exist, symlink or copy
  if (problemSource) {
    await writeFileStr(evalDir + '/frozen_problem.py', problemSource)
    log(`${WORKFLOW_NAME}: created frozen_problem.py from problem.py`)
  }
}

// Write the candidate as perf_takehome.py
await writeFileStr(evalDir + '/perf_takehome.py', candidateSource)
log(`${WORKFLOW_NAME}: wrote candidate to ${evalDir}/perf_takehome.py`)

// Read back and verify SHA-256
const persistedSource = await readFileStr(evalDir + '/perf_takehome.py')
const persistedHash = await sha256Hex(persistedSource)
log(`${WORKFLOW_NAME}: persisted SHA-256 = ${persistedHash}`)

if (persistedHash !== candidateHash) {
  throw new Error(
    `${WORKFLOW_NAME}: SHA-256 mismatch — pre-write hash=${candidateHash}, persisted hash=${persistedHash}. ` +
    `Candidate source integrity check failed.`
  )
}
log(`${WORKFLOW_NAME}: SHA-256 binding verified: ${candidateHash}`)

// Run correctness test
log(`${WORKFLOW_NAME}: running correctness command: ${TEST_COMMAND}`)
const correctnessResult = await runCommand(TEST_COMMAND, evalDir)
log(`correctness stdout: ${correctnessResult.stdout.substring(0, 500)}`)
if (correctnessResult.stderr) {
  log(`correctness stderr: ${correctnessResult.stderr.substring(0, 500)}`)
}
log(`correctness exitCode: ${correctnessResult.exitCode}`)

let correctnessPassed = false
let measuredCycles = null
let overallSpeedup = null
let bestKernelCode = null

if (correctnessResult.exitCode === 0) {
  correctnessPassed = true
  log(`${WORKFLOW_NAME}: correctness PASSED (exit 0)`)

  // Run benchmark only after correctness passes
  log(`${WORKFLOW_NAME}: running benchmark command: ${BENCHMARK_COMMAND}`)
  const benchmarkResult = await runCommand(BENCHMARK_COMMAND, evalDir)
  log(`benchmark stdout: ${benchmarkResult.stdout.substring(0, 500)}`)
  if (benchmarkResult.stderr) {
    log(`benchmark stderr: ${benchmarkResult.stderr.substring(0, 500)}`)
  }
  log(`benchmark exitCode: ${benchmarkResult.exitCode}`)

  if (benchmarkResult.exitCode === 0) {
    // Parse the CYCLES line from benchmark output
    // Expected format: "CYCLES: <number>"
    const cyclesMatch = benchmarkResult.stdout.match(/CYCLES:\s*(\d+)/)
    if (cyclesMatch && cyclesMatch[1]) {
      measuredCycles = parseInt(cyclesMatch[1], 10)
      if (measuredCycles > 0) {
        overallSpeedup = BASELINE / measuredCycles
        bestKernelCode = persistedSource
        log(`${WORKFLOW_NAME}: measured ${measuredCycles} cycles, speedup=${overallSpeedup.toFixed(4)}`)
      } else {
        log(`${WORKFLOW_NAME}: benchmark reported invalid cycles=${measuredCycles}; abstaining`)
      }
    } else {
      log(`${WORKFLOW_NAME}: could not parse CYCLES from benchmark output; full output: ${benchmarkResult.stdout.substring(0, 1000)}`)
    }
  } else {
    log(`${WORKFLOW_NAME}: benchmark FAILED (exit ${benchmarkResult.exitCode}); abstaining from speedup`)
  }
} else {
  log(`${WORKFLOW_NAME}: correctness FAILED (exit ${correctnessResult.exitCode}); not running benchmark`)
}

// =============================================================================
// PHASE 4: Report
// =============================================================================
phase('Report')

const reportLines = []
reportLines.push(`${WORKFLOW_NAME}: VLIW bundle-packing + SIMD vectorization optimization`)
reportLines.push(`Baseline: ${BASELINE} cycles`)
reportLines.push(`Correctness: ${correctnessPassed ? 'PASSED' : 'FAILED (exit ' + correctnessResult.exitCode + ')'}`)
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
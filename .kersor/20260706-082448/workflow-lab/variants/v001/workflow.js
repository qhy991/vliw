export const meta = {
  name: 'vliw-d3d4-joint-anneal',
  description: 'Landability-gated JOINT full-space simulated annealing over the D3_GATHER_MASK x D4_COLD_MASK synergy axis for a Python VLIW list-scheduler kernel (minimizes scheduled cycle count; arithmetic-identity-preserving by construction via mux<->gather / gather<->vload rerouting only).',
  whenToUse: 'When optimizing a Python VLIW list-scheduler kernel whose objective is scheduled cycle count, the live lever is the joint D3_GATHER_MASK x D4_COLD_MASK search (d3-alone -4, d4-alone -18, both -32 on the load engine), and the base single-position sweep + size-2/3 combo search has stalled at the 1132 local optimum. This variant replaces that sweep+combo method with a two-phase SA (rot-27 oracle collection then full-32 confirm) that co-perturbs both 64-bit masks together, landing only champs that pass the dual landability gate (PSPACE=1 correct AND < best AND PSPACE=0 correct AND <= bound). NOT for GPU/CUDA kernel generation; does NOT modify tests/.',
  phases: [
    { title: 'Orient', detail: 'Read directions/LESSONS.md (do-not-repeat registry) and measure current baseline cycles via parity_check.py && algebra_check_ported.py && tests/submission_tests.py for PSPACE=1 and PSPACE=0' },
    { title: 'Joint-SA', detail: 'Dispatch mechanical agent to run experiments/anneal_d3d4_joint.py (two-phase: rot-27 oracle collection then full-32 confirm with dual PSPACE gate) and read the champ JSON' },
    { title: 'Verify + land', detail: 'Set D3_GATHER_MASK/D4_COLD_MASK env to the champ masks and run the full dual gate (parity + algebra + submission_tests PSPACE=1 < best AND PSPACE=0 <= bound); ONLY if landable, edit perf_takehome.py shipped defaults (_d3champ tuple ~line 459, d4 default tuple ~line 486) and re-run the gate to confirm the shipped build reproduces the champ cycle count' },
  ],
  requiredSkills: [],
  optionalSkills: [],
  skill_binding_mode: 'prompt_reference_only',
}

const WORKFLOW_NAME = 'vliw-d3d4-joint-anneal'

// --- BEGIN inlined arg_guard (Workflow runtime parses scripts as bare scripts,
//                              not ES modules; static imports are rejected) ---
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

// --- BEGIN inlined agent-retry scaffolding (from _meta/scaffolding/agent-retry.js) ---
async function agentRetry(fn, opts) {
  const retries = (opts && opts.retries != null) ? opts.retries : 5
  let lastError = null
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const result = await fn()
      if (result != null) return result
    } catch (e) {
      lastError = e
    }
  }
  if (lastError) throw lastError
  if (opts && opts.allowNull === true) return null
  throw new Error(
    `agentRetry: "${(opts && opts.label) || 'agent'}" returned null after ${retries + 1} attempt(s) ` +
    `(agent skipped or terminal API failure after retries).`,
  )
}

function expect(obj, field, ctx) {
  if (obj == null || obj[field] == null) {
    throw new Error(
      `agentRetry: required field "${field}" is missing${ctx ? ' from ' + ctx : ''} ` +
      `(agent returned null or a malformed result after retries).`,
    )
  }
  return obj[field]
}

function guard(obj, field, fallback) {
  if (obj == null || obj[field] == null) return fallback
  return obj[field]
}
// --- END inlined agent-retry scaffolding ---

// =============================================================================
// vliw-d3d4-joint-anneal — fork_variant of vliw-sparse-mask-search
// =============================================================================
//
// Technique (ONE, canonical id = "instruction_scheduling"):
//   "Landability-gated JOINT full-space simulated annealing over the
//    D3_GATHER_MASK x D4_COLD_MASK synergy axis."
//
// Why this variant exists (the method-fit gap):
//   The base vliw-sparse-mask-search workflow runs a single-position sweep then
//   a size-2/3 combination search over the benefit window. Round-0 transfer
//   item 2 (failed_strategy, evidence=user_provided) records that this method
//   STALLS at the 1132 local optimum: the shipped 1120 champion needs FULL-SPACE
//   SA (64-bit bit-flip spanning both d3 rounds), which the sweep+combo method
//   cannot reach. The levers (D3_GATHER_MASK / D4_COLD_MASK) are exactly right
//   (transfer item 1: d3-alone -4, d4-alone -18, both -32 synergy on the load
//   engine); only the METHOD is wrong. This variant swaps the method for a
//   joint full-space SA while keeping the same levers, the same correctness
//   gates, and the same return envelope shape.
//
// The variant orchestrates an EXISTING seeded Python driver via Bash (exactly
// as vliw-anneal-optimizer orchestrates omni_anneal.py) — it does NOT generate
// GPU kernels, does NOT invoke a GPU profiler, and uses no wall-clock or PRNG
// host APIs. All randomness lives inside the Python annealer (seeded).
//
// Local driver (already exists in the worktree):
//   - experiments/anneal_d3d4_joint.py  two-phase SA: rot-27 oracle collection
//                                       then full-32 confirm with dual PSPACE gate
//   - tests/submission_tests.py         prints "CYCLES: N"; PSPACE env selects config
//   - parity_check.py / algebra_check_ported.py  arithmetic-identity gates
//   - directions/LESSONS.md             do-not-repeat registry (MUST read first)
//
// Dual landability gate (NON-REMOVABLE — the key correctness insight, verbatim
// from the base workflow and the sibling vliw-anneal-optimizer):
//   A win on the primary metric (PSPACE=1 cycles) that regresses the secondary
//   configuration (PSPACE=0) is NOT landable. The gate is:
//     PSPACE=1 correct AND c1 < ${BEST_KNOWN}  AND  PSPACE=0 correct AND c0 <= ${PSPACE0_BOUND}
//   The driver applies this gate internally before recording a champ; this
//   workflow RE-VERIFIES it on the landed env-injected build in Phase 3, and
//   re-confirms it on the shipped-source build after the perf_takehome.py edit.
//
// Arithmetic identity: masks only reroute mux<->gather / gather<->vload; the
// arithmetic graph is unchanged by construction. parity_check.py and
// algebra_check_ported.py still gate every champ — they are NOT removed.
//
// Usage:
//   Workflow({name: 'vliw-d3d4-joint-anneal', args: {
//     project_root: '/mnt/.../vliw-v120-d3d4-joint',
//     exp_dir: '/tmp/vliw_d3d4_exp',
//     iters: 2500, restarts: 3, seed: 42,
//     best_known: 1120, pspace0_bound: 1187,
//     collect: 1128, topk: 50,
//   }})
//
// =============================================================================

const PROJECT_ROOT = args.project_root || '.'
const EXP_DIR = args.exp_dir || '/tmp/vliw_d3d4_exp'
const ITERS = args.iters || 2500
const RESTARTS = args.restarts || 3
const SEED = args.seed != null ? args.seed : 42
const BEST_KNOWN = args.best_known || 1120       // current global best (PSPACE=1), strict <
const PSPACE0_BOUND = args.pspace0_bound || 1187 // secondary-config regression bound, <=
const COLLECT = args.collect || 1128             // oracle collect band for phase-1
const TOPK = args.topk || 50                     // max masks to full-confirm in phase-2

if (!PROJECT_ROOT) {
  throw new Error(`${WORKFLOW_NAME}: args.project_root is required (path to the vliw worktree)`)
}

// Model routing by agent role
const MODEL = {
  mechanical: args.model_mechanical || 'haiku',  // runs shell, parses output
  judgment: args.model_judgment || 'sonnet',     // planning + final report
}

// State
let baselineCycles = null
let baselinePspace0 = null
let lessonsDigest = ''
let champD3 = null                 // list of d3 gather positions (the champ)
let champD4 = null                 // list of d4 cold positions (the champ)
let champFull1 = null              // full-32 PSPACE=1 cycles of the champ (driver-reported)
let champFull0 = null              // full-32 PSPACE=0 cycles of the champ (driver-reported)
let champPath = ''                 // path to champ_d3d4.json on disk
let claimedVerdict = ''            // driver VERDICT line
let landable = false               // dual gate on the env-injected build
let shippedConfirmed = false       // shipped-source build reproduces champ cycles
let bestKernelCode = ''            // serialized {d3, d4} champ masks

// =============================================================================
// Phase 1: Orient — read LESSONS.md + measure current baseline cycles
// =============================================================================
phase('Orient')

const orient = await agentRetry(() => agent(`You are orienting a VLIW instruction-scheduler optimization run for the joint D3_GATHER_MASK x D4_COLD_MASK axis. Work inside the project worktree at ${PROJECT_ROOT}.

# Step 1 — Read the do-not-repeat registry (MANDATORY first)
Read ${PROJECT_ROOT}/directions/LESSONS.md in full. Extract:
- the current global best cycle count (PSPACE=1) and the PSPACE=0 bound,
- the binding-engine floor hierarchy (load/alu/valu/flow),
- every "verified kill" entry with its ID, measured result, and resurrection condition,
- any rule about mandatory re-anneal after op-count changes (Rule C),
- any note on the d3<->d4 load-engine synergy (d3-alone -4, d4-alone -18, both -32).

# Step 2 — Measure the current baseline cycles for BOTH configurations
Run from ${PROJECT_ROOT} (these are the canonical gates):
  1. \`cd ${PROJECT_ROOT} && python parity_check.py && python algebra_check_ported.py && python tests/submission_tests.py\`
     -> capture the line that prints "CYCLES: N" (this is PSPACE=1).
  2. \`cd ${PROJECT_ROOT} && PSPACE=0 python tests/submission_tests.py\`
     -> capture "CYCLES: N" (this is PSPACE=0).

If any command fails, report the failure verbatim and return success=false.

Return a JSON object with:
- lessons_digest: a concise string of the binding floors + killed directions + Rule C + the d3xd4 synergy note
- baseline_cycles: the PSPACE=1 cycle count (number) or null
- baseline_pspace0_cycles: the PSPACE=0 cycle count (number) or null
- success: boolean
- error: string (only on failure)`, {
  label: 'orient',
  phase: 'Orient',
  model: MODEL.mechanical,
  schema: {
    type: 'object',
    properties: {
      lessons_digest: { type: 'string' },
      baseline_cycles: { type: 'number' },
      baseline_pspace0_cycles: { type: 'number' },
      success: { type: 'boolean' },
      error: { type: 'string' },
    },
    required: ['lessons_digest', 'success'],
  },
}), { retries: 5 })

if (!orient.success) {
  throw new Error(`${WORKFLOW_NAME}: baseline gate failed in Orient: ${orient.error || 'unknown'}`)
}
lessonsDigest = orient.lessons_digest
baselineCycles = orient.baseline_cycles != null ? orient.baseline_cycles : BEST_KNOWN
baselinePspace0 = orient.baseline_pspace0_cycles != null ? orient.baseline_pspace0_cycles : PSPACE0_BOUND
log(`Orient: baseline PSPACE=1=${baselineCycles}, PSPACE=0=${baselinePspace0}, best_known=${BEST_KNOWN}`)
log(`LESSONS digest: ${lessonsDigest.slice(0, 200)}`)

// =============================================================================
// Phase 2: Joint-SA — run the joint full-space SA driver, read champ JSON
// =============================================================================
phase('Joint-SA')

// The driver runs a two-phase SA: Phase-1 pure rot-27 oracle SA (strict upper
// bound on full-32 realized) collecting distinct low-oracle joint masks;
// Phase-2 batch full-32 confirms the best masks and applies the dual PSPACE
// gate. Seed masks are the driver's defaults (the shipped 1120 champion):
//   D3_GATHER_MASK={0,1,2,3,4,37,39,40,46,54,58}, D4_COLD_MASK={25,26,27,29,31,34}.
const champOut = `${EXP_DIR}/champ_d3d4.json`
const paretoOut = `${EXP_DIR}/pareto.jsonl`

const annealResult = await agentRetry(() => agent(`Run the JOINT full-space simulated-annealing driver for the D3_GATHER_MASK x D4_COLD_MASK axis. Work inside ${PROJECT_ROOT}.

# Step 1 — Prepare scratch
\`\`\`bash
mkdir -p ${EXP_DIR}
\`\`\`

# Step 2 — Run anneal_d3d4_joint.py
Run exactly (the driver seeds itself from the shipped 1120 champion masks; do NOT pass extra seed-mask flags):
\`\`\`bash
cd ${PROJECT_ROOT} && python experiments/anneal_d3d4_joint.py \\
  --iters ${ITERS} \\
  --restarts ${RESTARTS} \\
  --seed ${SEED} \\
  --collect ${COLLECT} \\
  --topk ${TOPK} \\
  --gate1 ${BEST_KNOWN} \\
  --gate0 ${PSPACE0_BOUND} \\
  --out ${champOut} \\
  --pareto ${paretoOut}
\`\`\`
The driver prints a final line "BEST full PSPACE1=<n> PSPACE0=<n>" and a "VERDICT:" line, then "JOINT_DONE".

# Step 3 — Read the champ JSON
Read ${champOut}. It contains fields: best_full1, best_full0, d3 (list), d4 (list), seed_full1, seed_full0, n_collected, n_confirmed, verdict.

# Hard constraints
- Do NOT edit the champ JSON by hand.
- Do NOT modify tests/ or perf_takehome.py in this phase.
- Do NOT invent cycles; only report what the driver printed / what the champ JSON says.
- If the driver fails to produce a champ (e.g. exception, no JOINT_DONE line), return success=false with the error verbatim.

Return a JSON object with:
- champ_path: ${champOut}
- best_full1: number (the driver's full-32 PSPACE=1 champ cycles) or null
- best_full0: number (the driver's full-32 PSPACE=0 champ cycles) or null
- d3: array of integers (the champ d3 gather positions) or null
- d4: array of integers (the champ d4 cold positions) or null
- verdict: string (the driver's VERDICT line)
- n_collected: number
- n_confirmed: number
- success: boolean
- error: string (only on failure)`, {
  label: 'joint-sa',
  phase: 'Joint-SA',
  model: MODEL.mechanical,
  schema: {
    type: 'object',
    properties: {
      champ_path: { type: 'string' },
      best_full1: { type: 'number' },
      best_full0: { type: 'number' },
      d3: { type: 'array', items: { type: 'integer' } },
      d4: { type: 'array', items: { type: 'integer' } },
      verdict: { type: 'string' },
      n_collected: { type: 'number' },
      n_confirmed: { type: 'number' },
      success: { type: 'boolean' },
      error: { type: 'string' },
    },
    required: ['champ_path', 'success'],
  },
}), { retries: 5 })

if (!annealResult.success) {
  throw new Error(`${WORKFLOW_NAME}: joint SA driver failed in Joint-SA: ${annealResult.error || 'unknown'}`)
}
champPath = annealResult.champ_path
champFull1 = annealResult.best_full1
champFull0 = annealResult.best_full0
champD3 = annealResult.d3
champD4 = annealResult.d4
claimedVerdict = annealResult.verdict || ''
if (champD3 == null || champD4 == null) {
  throw new Error(`${WORKFLOW_NAME}: champ at ${champPath} has no d3/d4 mask lists`)
}
log(`Joint-SA: champ=${champPath}, full1=${champFull1}, full0=${champFull0}, verdict="${claimedVerdict}", d3=${JSON.stringify(champD3)}, d4=${JSON.stringify(champD4)}`)

// =============================================================================
// Phase 3: Verify + land — dual landability gate, then ship to perf_takehome.py
// =============================================================================
phase('Verify + land')

// The NON-REMOVABLE dual landability gate (verbatim contract from the base
// workflow and the sibling vliw-anneal-optimizer):
//   PSPACE=1 correct AND c1 < ${BEST_KNOWN}  AND  PSPACE=0 correct AND c0 <= ${PSPACE0_BOUND}
// A PSPACE=1 win that regresses PSPACE=0 is NOT landable. We re-verify on an
// env-injected build (D3_GATHER_MASK / D4_COLD_MASK env vars), and ONLY if
// landable do we edit perf_takehome.py shipped defaults and re-confirm.
const d3MaskJson = JSON.stringify(champD3.map(() => 1).map((_, i) => champD3.includes(i) ? 1 : 0))
// Build the 0/1 lists the env vars expect (length-64 JSON 0/1 arrays).
const d3BoolList = []
const d4BoolList = []
for (let i = 0; i < 64; i++) {
  d3BoolList.push(champD3.includes(i) ? 1 : 0)
  d4BoolList.push(champD4.includes(i) ? 1 : 0)
}
const d3MaskEnv = JSON.stringify(d3BoolList)
const d4MaskEnv = JSON.stringify(d4BoolList)

const verifyResult = await agentRetry(() => agent(`Run the DUAL LANDABILITY GATE on the champ joint masks, then ship ONLY if landable. This is the non-removable correctness gate. Work inside ${PROJECT_ROOT}.

# Champ masks (from the driver's champ JSON)
- D3_GATHER_MASK positions: ${JSON.stringify(champD3)}
- D4_COLD_MASK positions: ${JSON.stringify(champD4)}
- Driver-reported: full PSPACE=1=${champFull1}, PSPACE=0=${champFull0}, verdict="${claimedVerdict}"

# Step 1 — Env-injected build + full dual gate
Inject the champ masks via environment variables (the same plumbing perf_takehome.py already reads) and run the canonical gate for BOTH configurations. Run exactly:
\`\`\`bash
cd ${PROJECT_ROOT} && \\
D3_GATHER_MASK='${d3MaskEnv}' D4_COLD_MASK='${d4MaskEnv}' python parity_check.py && \\
D3_GATHER_MASK='${d3MaskEnv}' D4_COLD_MASK='${d4MaskEnv}' python algebra_check_ported.py && \\
D3_GATHER_MASK='${d3MaskEnv}' D4_COLD_MASK='${d4MaskEnv}' python tests/submission_tests.py && \\
D3_GATHER_MASK='${d3MaskEnv}' D4_COLD_MASK='${d4MaskEnv}' PSPACE=0 python tests/submission_tests.py
\`\`\`
Capture:
- parity_pass (boolean, true iff parity_check reports 0 violations)
- algebra_pass (boolean, true iff algebra_check reports ALL-PASS)
- pspace1_cycles (number, the "CYCLES: N" line from the PSPACE=1 submission_tests run)
- pspace0_cycles (number, the "CYCLES: N" line from the PSPACE=0 submission_tests run)

landable = parity_pass AND algebra_pass AND (pspace1_cycles < ${BEST_KNOWN}) AND (pspace0_cycles <= ${PSPACE0_BOUND})

# Step 2 — Ship to perf_takehome.py defaults (ONLY if landable)
If AND ONLY IF landable is true, edit ${PROJECT_ROOT}/perf_takehome.py to make the champ masks the shipped defaults:
- Near line 459, replace the _d3champ tuple with: ${JSON.stringify(champD3)}
  i.e. the line should read:  _d3champ = ${JSON.stringify(champD3)}
- Near line 486, replace the d4 default tuple with: ${JSON.stringify(champD4)}
  i.e. the line should read:  self._d4_cold_mask = [(i in ${JSON.stringify(champD4)}) for i in range(64)]
Do NOT touch any other line. Do NOT modify tests/. Do NOT modify the env-var plumbing.

# Step 3 — Re-run the gate on the SHIPPED source build (confirm reproduction)
After the edit, run with NO env vars set (so the new shipped defaults are used):
\`\`\`bash
cd ${PROJECT_ROOT} && unset D3_GATHER_MASK D4_COLD_MASK && python parity_check.py && python algebra_check_ported.py && python tests/submission_tests.py && PSPACE=0 python tests/submission_tests.py
\`\`\`
Capture shipped_parity_pass, shipped_algebra_pass, shipped_pspace1_cycles, shipped_pspace0_cycles.
shipped_confirmed = shipped_parity_pass AND shipped_algebra_pass AND (shipped_pspace1_cycles == pspace1_cycles) AND (shipped_pspace0_cycles == pspace0_cycles)

If NOT landable, do NOT edit perf_takehome.py. Leave the source untouched. Report landable=false with the cycle counts and which clause failed.

# Hard constraints
- Do NOT modify tests/.
- Do NOT relax the bounds. PSPACE=1 gate is strict < ${BEST_KNOWN}; PSPACE=0 gate is <= ${PSPACE0_BOUND}.
- A PSPACE=1 win that regresses PSPACE=0 is a FAIL.
- Do NOT edit perf_takehome.py unless landable is true.
- Do NOT manipulate the test harness, the reference's allocator, or the device free pool (no free-pool-scrubbing / zeroed-tensor pre-allocation tricks). The champ masks must win on real measured cycle count, not a manipulated reference match.

Return a JSON object with:
- parity_pass, algebra_pass: booleans
- pspace1_cycles, pspace0_cycles: numbers
- landable: boolean
- edited_perf_takehome: boolean (true iff you edited perf_takehome.py in step 2)
- shipped_parity_pass, shipped_algebra_pass: booleans (null if not edited)
- shipped_pspace1_cycles, shipped_pspace0_cycles: numbers (null if not edited)
- shipped_confirmed: boolean (null if not edited)
- failed_clause: string (only if not landable: "pspace1_correct" / "pspace1_lt_best" / "pspace0_correct" / "pspace0_le_bound")
- raw_output: string (last 1500 chars)`, {
  label: 'verify-land',
  phase: 'Verify + land',
  model: MODEL.mechanical,
  schema: {
    type: 'object',
    properties: {
      parity_pass: { type: 'boolean' },
      algebra_pass: { type: 'boolean' },
      pspace1_cycles: { type: 'number' },
      pspace0_cycles: { type: 'number' },
      landable: { type: 'boolean' },
      edited_perf_takehome: { type: 'boolean' },
      shipped_parity_pass: { type: 'boolean' },
      shipped_algebra_pass: { type: 'boolean' },
      shipped_pspace1_cycles: { type: 'number' },
      shipped_pspace0_cycles: { type: 'number' },
      shipped_confirmed: { type: 'boolean' },
      failed_clause: { type: 'string' },
      raw_output: { type: 'string' },
    },
    required: ['landable', 'edited_perf_takehome'],
  },
}), { retries: 5 })

landable = verifyResult.landable === true
const parityPass = guard(verifyResult, 'parity_pass', null)
const algebraPass = guard(verifyResult, 'algebra_pass', null)
const pspace1Cycles = guard(verifyResult, 'pspace1_cycles', null)
const pspace0Cycles = guard(verifyResult, 'pspace0_cycles', null)
shippedConfirmed = guard(verifyResult, 'shipped_confirmed', null)
const editedPerfTakehome = guard(verifyResult, 'edited_perf_takehome', false)
const failedClause = guard(verifyResult, 'failed_clause', '')

log(`Verify+land: landable=${landable} | parity=${parityPass} algebra=${algebraPass} | PSPACE=1=${pspace1Cycles} (gate < ${BEST_KNOWN}) | PSPACE=0=${pspace0Cycles} (gate <= ${PSPACE0_BOUND}) | edited=${editedPerfTakehome} shipped_confirmed=${shippedConfirmed}`)

// Serialize the champ masks as the "kernel code" (the d3/d4 masks ARE the
// optimized artifact for this VLIW scheduler — there is no GPU source to emit).
bestKernelCode = JSON.stringify({ d3: champD3, d4: champD4 })

// overall_speedup: cycle-count ratio (baseline / best). Higher is better. For a
// non-landable champ, overall_speedup is null — we do NOT ship regressions.
let overallSpeedup = null
if (landable && pspace1Cycles != null && baselineCycles) {
  overallSpeedup = baselineCycles / pspace1Cycles
}

// =============================================================================
// Final report
// =============================================================================
phase('Report')

const report = await agentRetry(() => agent(`Write a concise VLIW joint D3xD4 anneal optimization report.

# Inputs
- project_root: ${PROJECT_ROOT}
- technique: Landability-gated JOINT full-space simulated annealing over the D3_GATHER_MASK x D4_COLD_MASK synergy axis (canonical: instruction_scheduling)
- baseline PSPACE=1 cycles: ${baselineCycles}
- baseline PSPACE=0 cycles: ${baselinePspace0}
- best_known (PSPACE=1 gate, strict <): ${BEST_KNOWN}
- PSPACE=0 regression bound (<=): ${PSPACE0_BOUND}
- SA iters: ${ITERS}, restarts: ${RESTARTS}, seed: ${SEED}
- oracle collect band: ${COLLECT}, full-confirm topk: ${TOPK}

# Champ (from the driver)
- champ_path: ${champPath}
- driver-reported full PSPACE=1: ${champFull1}
- driver-reported full PSPACE=0: ${champFull0}
- d3 mask: ${JSON.stringify(champD3)}
- d4 mask: ${JSON.stringify(champD4)}
- driver verdict: "${claimedVerdict}"

# Dual gate result (env-injected build)
- landable: ${landable}
- parity: ${parityPass}, algebra: ${algebraPass}
- PSPACE=1: ${pspace1Cycles}  (gate: correct AND < ${BEST_KNOWN})
- PSPACE=0: ${pspace0Cycles}  (gate: correct AND <= ${PSPACE0_BOUND})
- failed_clause: ${failedClause || 'n/a'}

# Shipped-source confirmation
- edited perf_takehome.py: ${editedPerfTakehome}
- shipped_confirmed: ${shippedConfirmed}

# LESSONS digest (from Orient)
${lessonsDigest}

Write a report covering:
1. Whether the champ is landable and why (cite the dual gate numbers).
2. If NOT landable, name which clause failed and the mechanism (do NOT propose a fix — just report).
3. One-line note on whether the driver's full-32 PSPACE=1 matched the machine-verified env-injected PSPACE=1 cycle count (discrepancy is signal, not a bug to paper over).
4. Whether the shipped-source build reproduces the champ cycle count (shipped_confirmed).
5. Reminder of which killed directions from LESSONS.md are relevant to any future re-anneal.

Do NOT invent numbers. Do NOT propose relaxing the gate.`, {
  label: 'report',
  phase: 'Report',
  model: MODEL.judgment,
}), { retries: 5, allowNull: true })

return {
  baseline_cycles: baselineCycles,
  baseline_pspace0_cycles: baselinePspace0,
  best_known_gate: BEST_KNOWN,
  pspace0_bound: PSPACE0_BOUND,
  champ_path: champPath,
  champ_d3: champD3,
  champ_d4: champD4,
  driver_full1: champFull1,
  driver_full0: champFull0,
  driver_verdict: claimedVerdict,
  parity_pass: parityPass,
  algebra_pass: algebraPass,
  pspace1_cycles: pspace1Cycles,
  pspace0_cycles: pspace0Cycles,
  landable: landable,
  edited_perf_takehome: editedPerfTakehome,
  shipped_confirmed: shippedConfirmed,
  failed_clause: failedClause,
  overall_speedup: overallSpeedup,
  best_kernel_code: bestKernelCode,
  report: report,
}

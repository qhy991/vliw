# Rationale — `vliw-bundling-kernel-optimization`

## Routing gap

The Session's workflow-pool preflight reported `feasible_count=0`: no workflow
in the catalog declares `integration_patterns: ["custom_simulator"]`. The stock
catalog targets GPU build systems (standalone / registry_dispatch /
sol-execbench topologies); a repository-local CPU VLIW simulator with a Python
`KernelBuilder` seed is out-of-distribution, so the authoring escape fired
(`allow_workflow_authoring=true`, budget 1, fresh session — no prior artifact
was consulted).

## Technique

`instruction_scheduling` (canonical taxonomy id), method category
`instruction_mix_rebalance`. The seed builder emits exactly one slot per
bundle: 147,734 charged cycles at ~4% issue utilization while the machine
offers 23 issue slots per cycle (alu 12, valu 6, load 2, store 2, flow 1).
Two levers, both untouched by the seed:

1. **VLIW bundling** — pack independent slots from different engines into the
   same bundle dict (e.g. alu + load + flow in one cycle), respecting
   end-of-cycle write visibility (a consumer of a written scratch word must sit
   in a strictly later bundle) and at most one write per address per bundle.
2. **Batch-SIMD vectorization** — batch_size=256 divides into 32 vectors of
   VLEN=8; keep idx/val vectors resident in scratch, gather with load_offset
   lanes, run the six hash stages as valu ops over broadcast constants, and
   resolve the even/odd branch with vselect.

## Why this candidate shape

A two-phase advisory pipeline (Analyze → Generate → Report) with inline
structured-output schemas. The analyzer returns the bundle/vectorization plan
as data; the generator returns the complete KernelBuilder module as
`kernel_code` in one structured string; the host materializes and evaluates it.
The workflow never writes files, runs commands, or executes tests — DSH
`agent()` children are advisory/read-only.

## Fidelity boundary: `session_local_copy` (not `in_place_edit`)

The canonical task source named by `kernel_path` is read-only. The report
instructs the enclosing orchestrator to write the candidate to a Session-local
copy of the task directory, run the immutable correctness and benchmark
commands there (pinned interpreter — system python3 is 3.9.6 and cannot parse
the frozen `match` syntax), and bind all measured evidence to the candidate
identity. Metadata, rationale, and executable behavior all declare this same
boundary.

## `overall_speedup` on return

The returned `overall_speedup` is the generator's static estimate
(baseline_cycles / estimated_cycles), not a measurement. The enclosing
host-owned verifier re-measures via the immutable witness commands; its
measurement, not this estimate, is the terminal evidence.

## DSH Workflow-subset compliance

- Exactly one `export const meta`; the `META` alias duplicates the name literal
  because the export is not in body scope at dispatch time.
- Inline object-literal schemas; every `type` is one string; only
  `type/properties/required/additionalProperties` used.
- Only `agent`, `phase`, `log`, and `args` hooks; no `import`, no wrapper
  function, no timers, no `Date.now`/`Math.random`.
- Both agent prompts end by instructing a `structured_output` tool call naming
  the required keys verbatim; both results are null-guarded.
- Syntax gate `check-workflow-syntax.py`: passed.

## Metadata axes

`languages: ["python_reference"]`, `backends: ["python"]`,
`integration_patterns: ["custom_simulator"]` (verbatim from the frozen profile
— deliberately not broadened to `standalone`), `optimization_phases:
["portable_dsl"]`, `backend_portability: "explicit"`. The catalog contradiction
lint is satisfied: no specialized-vendor backend is claimed.

## Expected outcome

Slot-demand floors for the 4096-iteration shape: scalar-only packing about
9,899 cycles (14.9x); with batch-SIMD the per-lane gather and valu hash-chain
floors are about 2,048 cycles (~72x). The generator's estimate typically lands
between these; the 8.0x target sits well inside reachable headroom.

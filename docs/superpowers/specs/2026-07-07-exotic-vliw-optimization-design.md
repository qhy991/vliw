# Exotic VLIW Optimization Design

## Scope

Explore unconventional optimizations for the current 1092-cycle VLIW kernel in
`perf_takehome.py`.

The accepted boundary is strict:

- Do not modify `tests/` or `problem.py`.
- Final landed code must be bit-exact against `reference_kernel2`.
- Wrong-output probes may be used only as diagnostic lower bounds.
- No optimization lands unless it passes the project verification gate.

The current measured profile is:

```text
realized 1092
load  2071 / 2 = 1035.5
valu  6293 / 6 = 1048.8
alu  11160 /12 =  930.0
flow   859 / 1 =  859.0
F = (8 * valu + alu) / 60 = 1025.1
```

This means a sub-1000 result cannot come from a single ordinary engine shuffle.
The exploration must attack real gathers, the hash/traverse dependency chain, or
both.

## Approach 1: Local Boundary Shadowing

Try to extend the existing K5 x-space carry across selected gather boundaries by
building a local `node^K5` equivalent for only the schedule instances that need
it. Full-tree memory baking is already killed; this approach is narrower and
instance-driven.

Experiment shape:

- Identify rounds and emit instances where a gathered node blocks K5 deferral.
- Prototype local shadow reads or local correction ops behind a default-off flag.
- Prove equivalence with a standalone Python algebra harness before touching the
  kernel emitter.
- Measure whether the extra load/valu/flow work is smaller than the deleted
  stage-5 `^K5` and shorter critical path.

Kill if the local correction costs one hot valu or load slot per converted
instance without shortening realized cycles, or if equivalence requires rewriting
tree memory globally.

## Approach 2: Late-Round State Specialization

The submitted tests validate final values, not final indices. The current kernel
already skips the final index update; this approach looks one or two rounds
earlier for state that exists only to feed the final node fetch.

Experiment shape:

- Trace which `p`, `idx`, `addr`, and node-selection intermediates are consumed
  after rounds 13 and 14.
- Try specialized depth-3/depth-4 final-window emitters that compute only the
  state needed for the next valid node fetch and final value.
- Keep all final `values` bit-exact; do not rely on unchecked values being wrong
  unless they are outside the scoring surface by construction.

Kill if the specialization is equivalent to already-landed final index skipping,
or if it only deletes sub-floor valu work and regresses tail packing.

## Approach 3: Low-Scratch Candidate Encoding

Depth-4 and deeper gathers are the remaining hard load source. Resident tables and
flow vselect tournaments have been killed, but a smaller encoding may still exist
for a few sparse instances.

Experiment shape:

- Limit scope to sparse emit instances, not prefix masks.
- Test whether a small number of basis or delta vectors can reconstruct selected
  depth-4/depth-5 node candidates with less scratch than resident broadcasts.
- Prefer encodings that use setup-dead scratch or already-live temporaries.
- Reject any encoding that requires broad flow muxes, per-lane ALU forests, or
  node/addr pooling on the hot path.

Kill if random 32-bit tree values force one independent word per candidate, or if
the encoding raises flow/valu more than the removed scalar gathers lower load.

## Validation Gates

Every candidate follows the same gate sequence:

1. Algebra or state-equivalence check in a standalone script.
2. Schedule lower-bound probe on the real 1092 graph.
3. Default-off prototype in `perf_takehome.py` only if the first two gates pass.
4. Full verification:

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py
PSPACE=0 python tests/submission_tests.py
git diff -- tests/ problem.py
```

Only candidates with `CYCLES < 1092` and no `tests/` or `problem.py` diff are
eligible to land.

## Work Products

- Short experiment scripts under `experiments/` for probes that expose reusable
  evidence.
- A NO-GO note under `directions/` for any killed route with reproducible
  commands.
- A minimal `perf_takehome.py` change only for a verified win.


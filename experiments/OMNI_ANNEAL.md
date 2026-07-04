# Omni-anneal (dir #17) — unified genome + SA infra

`experiments/omni_anneal.py` drives simulated annealing over **any subset** of the
per-instance engine-mask classes, generalizing the two single-purpose scripts it
replaces (`anneal_cobind.py` = combine only; `anneal_extract.py` = combine +
extract). One framework, a class registry, config via CLI.

**Status:** infra landed on `explore/17-omni-anneal-infra` @ 1174 baseline.
Smoke-tested end-to-end (found a correctness-verified 1173 in 400 iters — see
`champ_omni.json`). The *full* production anneal is meant to run on the merged
#15+#18 graph, not this one; this window ships the infra.

## Why this is always correctness-safe

Every class here is a **1-valu-op ↔ 8-scalar-alu-op equivalence**: the two
emit forms compute the identical value (`v_alu` vs `v_alu_scalar`, same opcode),
so flipping the engine changes only packing/floors, never the result. `offset`
only reschedules independent vector work; `d3_gather_tail` swaps a mux for
gathers computing the same node. **F = (8·valu + alu)/60 is invariant under a 1:8
move** — the win is purely realized-cycle tail packing where an engine idles.

Mask/indexing *bugs* are not safe, though — so the anneal gates every shipped
champ on a real machine-vs-reference run (`check_correct`, ~11s) before writing
the JSON. Oracle/full evals alone never ship a champ.

## Genome classes (registry: `CLASSES` in `omni_anneal.py`)

| class | attr | kind | size | seed | flip bias |
|---|---|---|---|---|---|
| `combine` | `_combine_mask` | mask | 1536 | `_COMBINE_VALU_PSPACE_32x16` | 0.65 →alu |
| `extract` | `_extract_mask` | mask | 320 | `_EXTRACT_ALU_PSPACE_32x16` | 0.65 →alu |
| `xor` | `_xor_mask` | mask | 512 | depth≥4 rule (materialized) | 0.5 |
| `offset` | `_pos_offset` | offset | 32 | `_POS_OFFSET_PSPACE_32x16` | — |
| `d3_gather_tail` | `_d3_gather_tail` | scalar | 1 | 0 (∈[0,8]) | — |

Sizes and seeds are **re-probed from a fresh default build every run** — never
read from a stale champ. This is doc rule #2: after any op-count change the old
per-instance numbering mis-indexes, so we re-derive from emit order and re-seed
from the heuristic. (`xor` seeds by materializing the live `depth>=4` rule; the
smoke test confirms this seed is cycle-identical to `_xor_mask=None`.)

`flip bias` = P(proposing a True→False, i.e. valu→alu, flip). 0.65 matches the
prior scripts (valu is the binding floor post-#12, so we shed valu). Reset to
~0.5 — or invert — once a new op-count rebalance moves the binding engine.

## Proposal bias (doc rule #1)

Interior engine moves are F-neutral and usually hurt packing; the realized wins
live in the windup/drain where an engine idles. `_boundary_weights` up-weights
the first/last 15% of emit order (×4) so mask flips concentrate at the
boundaries. Classes are picked in proportion to their gene size.

## CLI

```bash
cd vliw

# seed metrics + correctness only (smoke test, ~12s)
python experiments/omni_anneal.py --classes combine,extract,xor,offset,d3_gather_tail --seed-only

# production run over a subset
python experiments/omni_anneal.py --classes combine,extract,offset \
    --iters 20000 --confirm-every 500 --out champ_omni.json

# warm-start from a prior champ (only genes whose class size still matches)
python experiments/omni_anneal.py --classes combine,extract,offset --resume
```

Flags: `--classes` (subset of the registry), `--iters`, `--seed`, `--out`,
`--confirm-every`, `--T0`, `--cooling`, `--resume`, `--seed-only`.

Champ JSON records `genome` + `{realized, oracle_rot, floors{valu,alu,load,flow,
F,tail}, op_counts, correct}` — the full `(valu,alu,load,flow,F,realized,tail)`
tuple the doc asks to track per champ.

## Objective / oracle

`ORACLE_ROT = 27` single-rotation build ≈ **0.34s** and equals the full-32
realized on the merged-floor graph (the scheduler keeps the best of K rotations;
rot27 happens to be that best here). SA optimizes the oracle; each new
oracle-best is re-checked full-32, and a genuine full-32 improvement is
correctness-gated before shipping. **Re-confirm rot27 is still a faithful proxy
after any op-count change** (rebuild seed-only and compare `rot27` vs `FULL32`);
if they diverge, either re-pick the oracle rotation or drop to full-32 evals
(~6s, 18× slower).

## Adding a class (when #15/#18 expose a new hook)

The movable classes in the #17 table (rem `val%2`, gather addr-add, s1/s5
`t1=val^K` / `t2=val>>s`, defer-traverse sub, muladd, vbroadcast) aren't yet
per-instance retargetable in `perf_takehome.py`. Each needs a two-step landing:

1. **In `perf_takehome.py`** — add an emit hook mirroring `v_alu_ex`/`_combine`:
   a counter `self._<cls>_no`, a mask `self._<cls>_mask` (default `None` ⇒
   identical to today), and at each call site pick `v_alu` vs `v_alu_scalar`
   (or flow `add_imm`) by `mask[no]`. Reset the counter in `gen_body`. Ship the
   annealed set as a module constant, applied in `build_kernel` when the mask is
   `None` (exactly like `_EXTRACT_ALU_PSPACE_32x16`).
2. **In `omni_anneal.py`** — one `CLASSES[...] = ClassSpec(attr, "mask",
   probe=lambda kb: kb._<cls>_no, seed=lambda kb: list(kb._<cls>_mask))` entry.
   Nothing else changes; `--classes` picks it up.

Gather addr-add and vbroadcast have a *third* engine option (flow `add_imm` /
store→mem) — model those as a small-int `scalar`/categorical gene per instance,
or split into two mask classes, rather than a single bool.

## Long-run recipe after an op-count rebalance (the mandatory re-tune)

#17 is the **required re-tuning pass after every op-count change** (the doc calls
this out explicitly). When #15/#18 land structural op deletions:

1. **Re-seed, don't resume.** Run without `--resume` so every gene re-seeds from
   the fresh heuristic — the old champ's per-instance indices are stale.
2. **Re-probe sizes** happens automatically; check the printed `sizes=` line
   against expectation (e.g. combine 1536, extract 320) to catch graph drift.
3. **Re-check the oracle proxy** (`--seed-only`: `rot27` must equal `FULL32`).
4. **Re-point the flip bias** if the binding engine moved (F floor vs valu/load).
5. Long run: `--iters 20000+ --confirm-every 500`, coordinate-descent by class
   first (`--classes combine`, then add `extract`, then `offset`) is often faster
   than all-at-once; then a joint polish over the union.
6. **Kill a class** if unlocking it never appears in accepted improving moves
   after ~10k proposals — drop it from `--classes` to shrink the search space
   (doc kill criterion). `d3_gather_tail` was 0-optimal on the 1208/1174 graphs;
   re-test on the merged graph before including it.

## Verify (unchanged baseline)

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py         # OK, CYCLES: 1174
PSPACE=0 python tests/submission_tests.py # OK, CYCLES: 1199
```

Shipping a champ into the kernel = sync its `genome` back to the module constants
(`_COMBINE_VALU_PSPACE_32x16`, `_EXTRACT_ALU_PSPACE_32x16`,
`_POS_OFFSET_PSPACE_32x16`, and any new class's constant) and re-run the full
gate. `omni_anneal.py` never edits `perf_takehome.py` — that promotion is a
deliberate, reviewed step.

## Success bar (doc §3)

`realized − max(F, load-floor, flow) ≤ 40` on the merged graph. Today on 1174:
`1174 − max(1078.4, 1070.5, 704) = 1174 − 1078.4 = 95.6` (the seed tail vs F).
Against the binding valu floor the tracked `tail` is 75.2. The prize is closing
that gap on the post-#15/#18 graph.

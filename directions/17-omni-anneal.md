# Direction #17: Omni-anneal — every op class gets an engine mask + boundary graph metamorphosis

**Thesis:** CP-SAT proved the scheduler is ≤1 cycle from optimal **for a fixed op
graph**, and 99% of bundles have a saturated engine — so the ~80-cycle tail gap
(realized 1179 vs valu floor 1099) can only fall by **changing the graph where it is
unsaturated: the windup and drain.** Today only two op classes are per-instance
retargetable (hash combines via `_combine_mask`, val^node via `_xor_mask`), plus
per-position offsets. Generalize: **every 1-valu-op ↔ 8-scalar-op equivalence becomes
an annealed per-instance choice**, and the windup/drain get graph shapes the mid-band
would never want.

Movable classes (all F-neutral — `F=(8V+A)/60` is invariant under 1:8 moves — but
worth 20–50 *realized* cycles at the boundaries where engines idle):

| class | today | choices | instances |
|---|---|---|---|
| hash combine | masked ✓ | valu / 8·alu | 1536 |
| val^node | masked ✓ | valu / 8·alu | 512 |
| `rem = val%2` | valu-locked | valu / 8·alu (fuse into an alu combine's lanes) | 448 |
| d2/d3/d4 bit-extracts (`&`,`<`) | valu-locked | valu / 8·alu | ~450 |
| gather addr-add | valu-locked | valu / 8·alu(shared scalar) / 8·flow `add_imm`(imm, zero scratch) | 192–256 |
| s1/s5 `t1 = val^K` | valu-locked | valu / 8·alu | ~800 |
| s1/s5 `t2 = val>>s` | valu-locked | valu / 8·alu | 1024 |
| defer-traverse sub (`perf_takehome.py:659`) | valu | valu / 8·alu | 128 |
| **muladd (drain-only)** | valu-locked | valu / 16·alu (`*` then `+` per lane) | last ~2 vectors' rounds |
| vbroadcast (setup/one-off) | valu | valu / 8·store→mem + 1 vload (only when load idle) | ~50 |

**Drain arithmetic that makes this worth it:** the last ~80 cycles have ~960 idle alu
slots while ~100–150 valu ops drain serially. Pushing even 60 of those to alu
(including muladds at 16/lane-pair) directly shortens the critical drain. Same story
mirrored in the windup (that's why `COMBINE_HEAD` exists — this is its generalization).

- **Priority: 3 (infra can start in parallel with #16; final anneal runs on the
  merged #15+#16+#18 graph).**
- **Expected:** tail gap 80 → **30–45**; i.e. −25 to −45 realized on whatever graph it
  runs on. This direction is also the *mandatory* re-tuning pass after every op-count
  change — budget SA compute for it.
- **Confidence: MEDIUM-HIGH** for ≥20 cycles (the head/tail combine masks already
  proved the mechanism); LOW for the full 50.
- **Effort:** 2–3 days infra + anneal compute.

---

## 1. Genome + objective

Genome = per-position offsets (32 ints, warm-start `_POS_OFFSET_PSPACE_32x16`) ⊕
per-instance engine masks for the classes above (bit-packed) ⊕ structural ints
(`D4_MUX_MASK` from #16, `D3_GATHER_TAIL`, defer-round set tweaks, mtmp group count).
Objective = realized `len(bundles)` from a **single-rotation fast eval** (the code
already supports `self._rotations` pinning for a ~6s eval — see
`perf_takehome.py:1063-1067`). Anneal loop = extend `experiments/anneal_cobind.py`
(alternating coordinate descent + SA restarts; keep every improvement as a JSON champ
like `champ_cobind.json`).

Two practical rules learned from #10/#14:
1. **Move ops toward the boundary engines only near the boundaries** — interior moves
   are F-neutral and usually hurt packing; bias proposals by emit-position percentile.
2. After ANY structural change (op deletion), the old champ masks mis-index —
   re-derive instance numbering from emit order and re-anneal from the heuristic seed,
   not from the stale champ.

## 2. Boundary metamorphosis specifics (beyond masks)

- **Drain:** last-vectors' r15 keeps *gathers* (load idle there) while mid-band r4
  converts to mux — the `D4_MUX_MASK` per-instance form covers this. `D3_GATHER_TAIL`
  re-sweep on the new graph (it was 0-optimal on the 1208 graph; the post-#15/#16
  graph is different).
- **Windup:** first ~40 cycles have an idle load engine (only 32 val vloads + consts):
  schedule-shift the 31 `vaddr` consts to flow `add_imm` (#18.4) and let heavy
  combine-on-valu head masks return (COMBINE_HEAD analog per class).
- **Store engine is 98% idle everywhere** — the only legal uses found: bcast-via-mem
  (table above) and rem-history spill (dead, see 19-moonshots §a). Don't force it.

## 3. Verify + kill criteria

Every champ: `python tests/submission_tests.py` must print OK (the anneal must gate on
correctness, not just cycles — engine moves are arithmetic-identical by construction,
but mask/indexing bugs are not).

- Track `(valu, alu, load, flow, F, realized, tail)` per champ in the JSON.
- **Kill (for a given class) if** unlocking it never appears in accepted moves after
  ~10k proposals — drop it from the genome to shrink the search space.
- **Success bar:** realized − max(F, load-floor, flow) ≤ 40 on the merged graph.

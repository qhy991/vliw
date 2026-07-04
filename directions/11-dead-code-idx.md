# Direction: Dead-idx elimination — round-10 traverse+wrap and the initial idx vloads are dead code

> **Origin:** found during the review of directions 01-10. None of the ten documents
> identified this, even though #8 §3.3 touched the wrap vselect (proposing a multiply
> substitution — strictly weaker than deleting it). Unlike most of the portfolio, this
> direction is **already implemented and measured on a scratch copy**: the op deletions
> land exactly as predicted and correctness passes; what remains is re-tuning the combine
> head/tail knobs to convert the floor drop into realized cycles.

---

## 1. Direction name + one-line thesis

**Dead-idx elimination.** Round 10's entire idx update — `rem` (`%`), `i2p1` muladd, add,
wrap compare (`<`), wrap `vselect` — is dead code, because its only consumer would be round
11, which is depth 0 and **never reads idx** (node comes from the `nb0` broadcast; the
depth-0 traverse writes idx fresh via the constant fold). The initial per-vector idx
`vload`s (and their `iaddr` address constants) are dead for the same reason: round 0 is
depth 0. Deleting all of it removes **128 valu + 32 flow + 63 load ops** from the binding
floors with zero algorithmic change.

---

## 2. Why this beats 1230 (measured, not estimated)

Two structural facts, both verified on `reference_kernel2` traces (seed 42, 256 elements):

1. **Round 11 never reads idx.** `_emit_vec_round` at depth 0 acquires the node from
   `c["nb0"]` and computes `idx = 1 + rem` without reading the incoming idx
   (perf_takehome.py lines 406, 436-438). So every op in round 10 whose only purpose is to
   produce idx is dead: `%` (1 valu), muladd (1 valu), `+` (1 valu), `<` (1 valu), wrap
   `vselect` (1 flow) per vector — `4 valu + 1 flow` × 32 vectors = **128 valu + 32 flow**.
2. **Round 0 never reads idx either** (same depth-0 structure), so the 32 idx `vload`s and
   the 31 `iaddr` scratch-consts that feed them are dead: **63 load ops**.

Bonus fact (makes the deletion airtight but is not needed for it): the round-10 wrap is
**unconditional** — at depth 10, `idx ∈ [1023, 2046]`, so `2·idx+1+rem ≥ 2047 = n_nodes`
always; verified 256/256 elements wrap to 0. Even if some future round *did* read
post-round-10 idx, it could be a broadcast zero.

**Measured result on the scratch implementation (`/tmp/vliw_probe`, full 32-rotation
build):**

```
                 baseline      after deletion     delta (predicted)
valu             7055          6927               -128  (-128 ✓)
flow              736           704                -32   (-32 ✓)
load             2196          2133                -63   (-63 ✓)
alu             13456         13456                  0
valu floor       1175.8        1154.5             -21.3
combined floor   ~1165         1147.9             -17
CYCLES           1230          1234               +4  (!!)  <- before re-tuning
correctness      —             OK on 3 random seeds (full Machine run vs reference)
```

The +4 is the known packing-noise / stale-knob effect: `_combine_head=10/_combine_tail=100`
were swept against the *old* op profile (OPTIMIZATION_NOTES §5 warns neighboring configs
jump 1230-1240). The floors dropped exactly as computed; the schedule must be re-tuned to
ride the new floor. This is the live demonstration of the portfolio-wide caveat "a floor
drop does not automatically convert to cycles."

**First coarse re-sweep (10 configs, run during review) already recovers it:**

```
head=20 tail=120 -> 1228   <- NEW BEST (beats 1230)
head=14 tail=110 -> 1229
head=16 tail=130 -> 1230
head= 6 tail= 80 -> 1231
head=10 tail=100 -> 1234   (stale old optimum)
head= 0 tail=100 -> 1237
head=40 tail=200 -> 1255
```

The optimum moved exactly as predicted (more combines vectorized onto valu in the tails,
since the deletion freed valu). Neighbors 1228/1229/1230 corroborate the region. The
head/tail knob is correctness-free by construction (identical arithmetic, engine
reassignment only), so 1228 stands pending the standard `submission_tests.py` gate. A
finer grid around (20,120) — and a joint sweep with `step`/priority-key — is the obvious
next step and may find a couple more cycles.

---

## 3. Mechanism: exactly what changes in `perf_takehome.py`

Three small edits, all in `build_kernel` / `gen_body`. No scheduler change, no new scratch.

1. **Generalize `skip_idx_update`** (gen_body, line ~699). Replace
   `skip_idx_update=(r == rounds - 1)` with:

   ```python
   # skip idx update when nothing downstream reads it: (a) final round;
   # (b) next round is depth 0, which never reads idx. (b) also deletes the
   # round-10 wrap compare+vselect, since the wrap round always precedes a
   # depth-0 round by construction (depth = r % (fh+1)).
   skip = (r == rounds - 1) or ((r + 1) % h1 == 0)
   ```

   This is shape-generic: for any (forest_height, rounds), every round preceding a
   depth-0 round is skippable, and every wrap round (depth == fh) is exactly such a round.

2. **Delete the idx vloads** (the vload loop, lines ~657-664): drop the
   `("vload", vs[j]["idx"], ia)` op; keep the val vload.

3. **Drop the dead `iaddr` consts** (per-vector scratch loop, lines ~624-631, the
   `n_groups == 1` branch): stop emitting `scratch_const(IIP + j*V)` for j>0. (For
   `n_groups > 1` the iaddr alu ops become dead too; the frozen shape is n_groups==1 so
   this is optional hygiene.)

Correctness argument: idx is per-vector state whose only readers are (a) node acquisition
at depth ≥ 1, (b) the traverse muladd, (c) the wrap compare. Rounds 11-15 recompute idx
from scratch starting at the depth-0 constant fold, so no value produced by round 10's
update escapes. The stored idx array is not validated by the scoreboard (the build already
skips the idx vstore — "Without Indices" category).

---

## 4. Day-1 experiment — ALREADY RUN; what remains

Already done during review (scratch copy at `/tmp/vliw_probe`, diffable against the repo):

- Build: op deltas match prediction exactly (table in §2).
- Correctness: full `Machine` run vs `reference_kernel2` on 3 random seeds — OK.

Remaining (hours, not days):

1. **Re-sweep `_combine_head × _combine_tail`** — the coarse 10-config probe already ran
   during review and found **(head=20, tail=120) → 1228 < 1230** with corroborating
   neighbors (see §2). Refine the grid around (20,120) (e.g. head ∈ 16..28 × tail ∈
   104..144 step 4) for a few more cycles.
2. If no (head, tail) config beats 1230, sweep jointly with `step ∈ {2,4,8}` and the 5
   scheduler priority keys — the deletion changed the DAG shape near the drain, where the
   response surface is noisy.
3. Final gate, as always:

   ```bash
   git diff origin/main -- tests/     # MUST be empty
   python tests/submission_tests.py   # MUST print OK + CYCLES
   ```

**Kill criterion:** none for the deletion itself — it is provably correct and strictly
reduces every floor; there is no configuration in which keeping dead code helps a
throughput-bound schedule *after* re-tuning. If the full re-tune still lands ≥1230, ship it
anyway as the base for directions #2/#3 (their op deletions stack on the same rounds and
the combined floor drop is what matters).

---

## 5. Risks & likely failure modes (honest)

1. **Realized-cycle risk (observed, not hypothetical):** the naive drop-in measured 1234.
   The win is real at the floor level (−17 combined) but is currently being eaten by stale
   scheduler knobs. If the head/tail re-sweep cannot recover it, the standalone win may be
   0-10 cycles rather than ~17. Even then the direction is worth landing (see kill
   criterion).
2. **Round-10's deleted ops sat partly in slack regions.** Round 10 spans diagonals
   ~10-17 — mostly the saturated middle/pre-drain, which is favorable; but some vectors'
   round-10 lands in the drain where valu had idle slots, diluting the realized win.
3. **Interaction with #2 (K5-deferral):** round 10 is a deferral round there; with the
   traverse deleted, #2's parity-swap for round 10 becomes moot (one less seam). The two
   directions compose cleanly — verify the combined variant separately.
4. **No new correctness surface**: no arithmetic changes, no new scratch, no engine
   rebalance. The only failure mode is a wrong skip condition; the shape-generic form in
   §3.1 is checked by `submission_tests.py`.

---

## 6. Expected payoff + confidence + effort

- **Floor movement (measured):** valu 1175.8 → 1154.5; combined ~1165 → 1147.9.
- **Realized cycles (measured):** **1228 at (head=20, tail=120)** from the first coarse
  10-config re-sweep; likely **1220-1228** after a finer grid. The floors are banked for
  #2/#3 to stack on regardless.
- **Confidence the *deletion* is correct and floor-lowering: proven** (measured, 3-seed
  correctness). **Confidence it beats 1230 standalone: proven at the bundle-count level**
  (1228 measured; final `submission_tests.py` gate still required as always).
- **Effort: 0.5-1 day** (the implementation exists; port the 3 edits from
  `/tmp/vliw_probe/perf_takehome.py`, run the sweep, validate).

---

## 7. Dependencies / prerequisites

- **None.** No libraries, no new scratch (it *frees* 31 const slots), no scheduler change.
- **Sequencing: land this FIRST.** It is the cheapest verified floor reduction in the
  portfolio, it simplifies #2 (removes the round-10 seam) and #3 (removes round-10 from
  the idx-audit surface), and every other direction's baseline measurements should be
  re-taken on top of it.
- The scratch implementation with all three edits applied is at `/tmp/vliw_probe/`
  (diff against the repo's `perf_takehome.py` to port).

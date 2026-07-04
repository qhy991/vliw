# Direction: Depth-Interleaved SIMD Layout

> **VERDICT: DEPRECATED (July 2026).** Same windup/drain target as #04 and #10. Per-position
> offset (`_POS_OFFSET_32x16`) already found a strongly non-uniform emission order (1230→1208).
> CP-SAT shows the middle band [200–1000] is triple-saturated — depth-mixing cannot help there.
> Archive only.

## 1. Direction name + one-line thesis

**Depth-Interleaved SIMD Layout (round-phase staggering of the batch).**

The 32 vectors currently all execute *the same round r* at roughly the same wall-clock time (the diagonal emission staggers them by only `ppos[j]//step` rounds, so they clump into 4-wide bands of identical depth). Because a round's engine mix is a strong function of its **depth** (no-gather depths 0-3 are ALU-heavy with zero load; gather depths 4-10 are load-heavy with slack ALU), a bundle built from same-depth vectors is *monochromatic* and cannot fill both engines. **Thesis: give each vector a different round-phase so that at every wall-clock bundle the in-flight vectors span complementary depths (some gather, some no-gather), letting each depth's idle engine soak up the other depth's surplus — directly filling the windup/drain valu/load holes that hold us 56-70 cycles above the throughput floor.**

## 2. Why this could beat 1230 (quantitative, tied to verified floors)

### 2.1 The per-depth engine mix is highly non-uniform (measured, not assumed)

Instrumenting `_emit_vec_round` (wrapping it in `build_kernel`) to count engine ops for **one vector-round** at each depth gives (verified on shape `fh=10, rounds=16, batch=256`):

```
depth  alu  valu  load  flow   | character
  0     8    14    0     0     | no-gather, valu-heavy (const-folded d0)
  1    32    13    0     1     | no-gather, ALU-heavy (v_alu_scalar XORs)
  2    32    14    0     3     | no-gather, ALU-heavy + flow (4-way mux)
  3    32    15    0     7     | no-gather, ALU-heavy + flow-heavy (8-way mux)
  4-9  24    14    8     0     | GATHER: load-heavy, ALU moderate
 10    24    15    8     1     | gather + wrap
```

The two engines that bind (alu floor 1122-1195, valu floor ~1169-1171) are loaded **very differently by depth**: no-gather rounds put 32 ops on ALU and 0 on load; gather rounds put 8 on load and only 24 on ALU. A bundle made of only no-gather vectors wastes the load engine and over-subscribes ALU; a bundle of only gather vectors under-uses ALU. Mixing them balances both.

### 2.2 The current layout makes windup/drain monochromatic — this is the recoverable gap

Reconstructing which `(vector, round)` pairs land on each emission diagonal (`K=32, step=4, rounds=16, n_diag=23`, rot=0) shows the depth spread per diagonal:

```
diag  0: 4 vec-rounds, ALL depth 0            (windup: valu-heavy only,  no load, ALU light)
diag  1: 8 vec-rounds, depths {0,1}           (windup)
diag  2:12 vec-rounds, depths {0,1,2}
diag  3:16 vec-rounds, depths {0,1,2,3}       (all no-gather => load engine 100% IDLE)
diag  4:20 vec-rounds, depths {0..4}          (first gather appears)
...
diag  7:32 vec-rounds, full pipeline (steady state, both engines ~100%)
...
diag 22: 4 vec-rounds, ALL depth 4            (drain)
```

This is the mechanistic root of the notes' observation *"windup [0-100]: alu 83% / valu 43%; drain [1100-1249]: alu 14-94% / valu 2-45%."* Diags 0-3 (~the first ~64-100 bundles) run **only depths 0-3**, which are exactly the no-gather, ALU-heavy, **load=0** rounds — so the load engine sits at 0% and there are too few valu ops to keep valu busy. Diags 16-22 (drain) similarly thin out. The middle (diags 7-15) already spans 8 distinct depths simultaneously and is jointly saturated — untouchable, matching the notes.

**The gap is entirely in the tails, and its cause is now precise: the tails are depth-monochromatic.** The 1174 combined-throughput floor (and the ~1161 figure for the *current* alu/valu split) is unreachable while ~11 tail diagonals run at <32 vectors AND at a single depth-band. If interleaving lets tail bundles mix gather+no-gather work, each tail bundle does more useful vector-equivalent work.

### 2.3 How many cycles are on the table

Current = 1230. Combined throughput floor for the present op split = **~1161** (measured: `valu 7022 + alu 13456/8 = 8704 vector-equiv / 7.5 per bundle = 1161`); the notes' canonical floor is 1174 for a different alu/valu split. The notes attribute ~17 pure-stall bundles and locate the rest of the 1230-1161 ≈ 69-cycle surplus in windup/drain packing. This direction attacks that 69-cycle surplus directly. Realistically, tail bundles can never be perfectly full (there genuinely are fewer vectors alive at the very ends), so a plausible recovery is **20-50 cycles → 1180-1210**, with an optimistic 1180 if the interleave also lets the head/tail `_combine` rebalance be retired (freeing it to help the middle).

## 3. Mechanism: exact changes in `perf_takehome.py`

The load/store contiguity constraint (verified: `problem.py:279 vload`, `:293 vstore` both take a scalar base `addr` and touch `addr..addr+7` — **no gather, no shuffle**) means we **cannot** repack elements across lane boundaries. The only free knob is **which round each vector is at when a given other vector is at its round** — i.e. the *phase*, not the lane packing. Two concrete, contiguity-safe variants:

### Variant A — Phase-offset the vectors (change `gen_body` in `build_kernel`, ~lines 679-716)

Each vector `j` runs all 16 rounds regardless. Today vector `j`'s round `r` is emitted on diagonal `r + ppos[j]//step`, so vectors in the same `step`-block share a phase and cluster at the same depth. **Change: give each vector its own round-phase offset `phi[j]` spread across the full `0..rounds-1` range**, so that at any diagonal the live vectors span depths `{(diag - phi[j]) % h1}` which — if `phi[j]` are spread — covers many depths at once, including during windup/drain.

Concretely, in `gen_body(rot)` (line 679) replace the block-based start `r = diag - ppos[j]//step` (line 692) with a per-vector phase:

```python
# phi[j] in 0..rounds-1, chosen to spread depths. Simplest: phi[j] = (j * PH) % rounds
# for a stride PH coprime-ish to h1 so consecutive vectors hit different depths.
r = diag - phi[j]
if 0 <= r < rounds:
    self._emit_vec_round(vs[j], c, r % h1, j=q, skip_idx_update=(r == rounds - 1))
```

with `n_diag = max(phi) + rounds` and `phi` precomputed. The scheduler (untouched) then sees, on any given diagonal, a mix of `r%h1` depths and is free to co-issue a gather vector's 8 loads with a no-gather vector's ALU XORs. **This is pure emission reordering + a new `phi` array; no ISA op changes, no correctness change (every vector still runs every round in order; only the interleave with *other* vectors changes, and cross-vector ops share no scratch — see scheduler dep construction, `perf_takehome.py:97-116`, which only creates edges between ops touching the same address).**

Key sub-decision: **`phi` should be spread modulo `h1=11`, not modulo `rounds=16`.** Because depth = `round % 11`, two vectors whose phases differ by 11 are at the *same* depth. To maximize depth diversity per bundle we want `{phi[j] % 11}` to cover all 11 residues as evenly as 32 vectors allow (roughly 3 vectors per residue). Candidate: `phi[j] = (j * s) % rounds` swept over `s`, plus a direct residue-balanced assignment `phi[j] = j % 11` (capped at `rounds-1`).

### Variant B — Two-phase batch split (coarser, lower-risk fallback)

Split the 32 vectors into two halves that start `rounds//2 ≈ 8` rounds apart, so that while half A is in its no-gather windup (depths 0-3) half B is already in gather steady state (depths 4-10) and vice-versa on the drain. This is a special case of A with `phi[j] ∈ {0, 8}`; cheaper to reason about and to sweep, and it half-overlaps the two tails so the drain of A coincides with the windup of B.

### Interaction with the existing `_combine` head/tail rebalance (lines 301-313, 230-233)

The current `_combine_head=10 / _combine_tail=100` policy is a *proxy* for "this combine is in the windup/drain, put its XOR on the idle valu." Once depths are interleaved, the emit-order→schedule-position correlation the counter relies on **changes**, so `_combine_head/_tail` must be **re-swept** (or, ideally, retired in favor of a depth-aware rule: put the XOR on valu only for gather-depth vectors, which already have load pressure and ALU slack — but note depth<4 currently uses `v_alu_scalar` for `val^=node` at line 407-408, an interacting choice). Treat the combine policy as a joint knob with `phi`.

## 4. Day-1 experiment (smallest thing to validate/kill fast)

Because a full `build_kernel` runs the 32-rotation search and takes **~190s** (measured), do **not** put a `phi` sweep inside the rotation loop on day 1. Instead:

1. **Add a `phi` array to `gen_body` and fix `rot=0`** (bypass the rotation search) to make each build ~6s. Smallest change: edit line 692 as in Variant A, add `phi` as a `build_kernel` local, and temporarily replace the `for rot in range(K)` loop (line 719) with `for rot in [0]`.

2. **Measure cycles by counting bundles** (verified: `cycles == len(kb.instrs)` for `n_groups==1`), no simulation needed:

```bash
python3 -c "
from perf_takehome import KernelBuilder
kb = KernelBuilder()
kb.build_kernel(10, 2047, 256, 16)   # 2047 = 2**11-1 nodes for fh=10
print('CYCLES:', len(kb.instrs))"
```

3. **Sweep a handful of `phi` policies** at `rot=0`: (a) baseline `phi[j]=ppos[j]//4` reproduced (sanity: must give the same as current rot=0), (b) `phi[j]=j % 11`, (c) `phi[j]=(j*3)%16`, (d) Variant B `phi[j]=8*(j>=16)`. Print CYCLES for each. **Kill criterion:** if none of (b)-(d) beats the `rot=0` baseline by even 1 cycle *before* re-tuning `_combine`, and a quick per-bundle engine-occupancy dump (reuse the profiling wrapper from the notes) shows the windup/drain load engine is *still* ~0% busy, the interleave isn't reaching the scheduler — likely because `_emit_vec_round`'s intra-vector dependency chain (hash is 6 strict serial stages) forces same-depth clumping regardless. That would be a strong kill signal.

4. **Only if a `phi` shows promise at rot=0**, re-enable the rotation search AND re-sweep `_combine_head/_tail` jointly (this is the expensive multi-hour step). Validate final correctness with `python tests/submission_tests.py` (must print `OK` and `CYCLES: <n>`).

## 5. Risks & likely failure modes (honest)

- **The middle is already saturated and already spans 8 depths** (diags 7-15 above). Interleaving can only help the ~11 tail diagonals; if the scheduler is already opportunistically pulling future gather work forward into the windup (it has global freedom — `run()` in `Scheduler` considers *all* unscheduled ready ops each bundle, lines 152-172), then the "monochromatic tail" may be a *dependency* artifact, not an *emission-order* one, and reordering emission won't unstick it. The notes explicitly flag *"naive deeper pipeline via emission reorder"* as dead — this must be more than a reorder; it must change the **depth composition of the ready set** in the tails.
- **Head/tail `_combine` coupling:** the current 1230 leans on a finely-swept head=10/tail=100. Any `phi` change invalidates that sweep, so a naive A/B against 1230 will look *worse* until `_combine` is re-tuned. Must compare at *matched, re-tuned* combine params, not against the tuned-for-old-layout 1230.
- **Scratch pressure:** spreading phases widens `n_diag` and the number of simultaneously-live vectors' temporaries. Current design deliberately reuses `node`/`addr` as hash temps to fit 32 vectors in `SCRATCH_SIZE=1536` (comment at lines 612-617). If interleaving needs more `mtmp` groups live at once, it could OOM scratch (the notes hit OOM at `NUM_MTMP_GROUPS>=6`). Mitigate: keep per-vector footprint identical; only phases change.
- **Contiguity is real and unshuffleable** — confirmed at `problem.py:279/293`. Any layout idea that needs a vector lane to hold elements from non-contiguous batch positions is dead on arrival. Variants A/B avoid this entirely (each vector still owns a contiguous 8-element slice; only its *time-phase* changes).
- **Packing noise:** the notes warn the tail response surface is noisy (±3-10 cycles). A 5-cycle "win" from a lucky `phi` is not structural. Require neighborhood corroboration before believing any result.

## 6. Expected payoff & effort

- **Payoff:** optimistic **1180** (if ~50 cycles of tail gap recovered and `_combine` freed to aid the middle), likely **1205-1225** (20-25 cycles). Below 1174 is *not* expected from this direction alone — this attacks scheduler/tail-packing, not op count.
- **Confidence: low** that it beats 1230 at all (the scheduler's global freedom may already be extracting most of the interleave benefit; the notes' repeated null results on emission-reorder variants are a real prior).
- **Effort:** Day-1 kill experiment ≈ 0.5 day (fast `rot=0` sweeps). If promising, joint `phi` × `_combine` × rotation re-tuning is **2-4 days** because each full build is ~190s and the search is 2-3 dimensional. Budget a build-time optimization (cache the dependency graph, or prune the rotation search to the top few) as a prerequisite if the sweep space is large.

## 7. Dependencies / prerequisites

- **Build-time reduction is a soft prerequisite for the sweep phase**: the 32-rotation search at ~190s/build makes any 2D sweep painful. Before the expensive phase, either (a) restrict `rot` to a small promising set, or (b) memoize the `deps` construction across rotations (the RAW/WAR/WAW graph in `Scheduler.schedule` is recomputed every rotation but the *structure* is largely rotation-invariant). No external library needed.
- **Scratch budget:** confirm `self.scratch_ptr <= 1536` after any layout change (assertion at `perf_takehome.py:244`). No new budget required if per-vector footprint is held constant.
- **A per-bundle engine-occupancy profiler** (the tool the notes used to find "windup alu 83%/valu 43%") — reconstruct it as a small script that, given `kb.instrs`, prints per-bundle `len(bundle.get(engine,[]))` vs `SLOT_LIMITS`. This is the primary instrument for confirming the interleave actually fills tail load/valu slots, independent of the noisy cycle count.
- **No test changes** — `tests/` and `frozen_problem.py` are untouchable (hard rule). All edits confined to `KernelBuilder.build_kernel` / `gen_body` / `_combine` in `perf_takehome.py`.
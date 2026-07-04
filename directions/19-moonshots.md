# Direction #19: Moonshots — rare, higher-risk paths beyond the ~1050 wall

The op-count route plus #17's anneal caps out somewhere around 1050–1070 realized. To
get to 1000, we need at least one of these — they're rarer, mostly untried, and each
has a concrete kill test up front so you don't burn a worktree on a dead one. **Do
these in isolated worktrees; none should block #15/#16/#17/#18.**

Ordered by rough expected value × probability, best first.

---

## §a — 2-round hash fuse (algebra-first; kill fast)

**Idea.** `hash(hash(v ^ n_a) ^ n_b)` for a *fixed* `n_a, n_b` — could a pair of
adjacent broadcast/mux rounds fuse into fewer than 2× hash ops? The hash is a mix of
`+`, `<<` (both affine over ℤ/2^32) and `^`, `>>` (both affine over 𝔽₂ᵏ). No single
algebra makes it linear. But hash-stage 5's `t2 = a >> 16` throws away the low 16
bits of `a`, so **the top 16 bits of `hash(v)` do not depend on the low 16 bits of the
pre-s5 state**. That's a real information bottleneck — worth 30 minutes to see if it
lets any two-round subformula collapse.

**Kill test (do this first, ~1 hour):**
```python
# Build a symbolic ADD/XOR/SHIFT/MUL DAG for hash(hash(v^na)^nb) with na,nb constants.
# Feed a small BDD/CVC5 to check if the DAG can be realized with < 24 valu-locked ops
# (current: 2 rounds × 7 valu-locked = 14 — so we need < 14 to beat the status quo).
```
The BDD will either return an equal-or-smaller DAG (rare, huge win) or confirm the
lower bound (kill in one hour). Do **not** hand-craft rewrites; SMT or superoptimizers
(Souper, Rosette) are the right tool.

**If it works:** every d0→d1 and d1→d2 boundary in the schedule fuses (~10 pair
instances × 2 rounds × 32 vecs = ~640 potential fusions, capped by node availability).
Realized 1179 → hard-to-estimate but potentially ≤950.

**Confidence: LOW (~10%). Expected value: HIGH.** Run in one worktree.

> **RESOLVED — NO-GO (2026-07-05).** Killed algebra-first in ~1h; 0 ops saved.
> hash is a bijection (constructive per-stage inverse) with full 32-bit
> bit-liveness across the round boundary, so the stage-5 `>>16` bottleneck is
> intra-hash only and never becomes cross-round dead code; structurally `nb` is
> a parity-dependent runtime gather, not a constant. See
> `19a-2round-fuse-NOGO.md` + `experiments/fuse_kill_test.py` (branch
> `explore/19a-2round-fuse`).

---

## §b — d5 partial mux (2-level dispatch, cost 2 vloads + 8 broadcasts + 8 gathers-per-instance)

d5 has 32 candidate nodes (tree[31..62]). Full 32-way mux costs 31 flow/instance —
kills the flow wall. But: split idx&24 into a **4-way outer mux** selecting one of
four 8-element groups, then still gather within group. Per instance: 3 flow (outer)
+ 8 loads → **same load cost, 3 extra flow, no valu saved** — dead as stated.

**The variant that could work:** *cross-vector shared outer mux.* All 32 vectors at
d5 share the same tree, so if their `idx>>3` happens to cluster (they don't — random
hashes), one shared gather could feed 8 vectors' final selects. **Kill test:** measure
`|distinct(idx>>3) across 32 vecs|` in the value trace for r5, r6. If ≤ 8, this
buys ~50% of d5's load. If > 24 (likely — hash randomness), dead.

**Confidence: LOW (~15%). Expected value: MEDIUM.** ~1 day, gate on trace measurement.

---

## §c — Store-broadcast pipe (turn setup into a load/store microloop)

Setup currently spends ~30 valu ops on vbroadcasts (`nb0..nb14`, `d3_*`, K5-baked
variants). Store engine is idle *everywhere* including setup. Alternative: write the
scalar to mem[some_scratch] then vload it — **1 store + 1 vload = 2 setup cycles
for what today takes 1 valu broadcast**. Net-negative in isolation.

**But** the composite move helps when combined with #16's 16-broadcast setup burst:
that burst serializes on the valu engine (16 vbroadcasts in a row → 3 cycles minimum
even with 6 slots). If we split it half-and-half — 8 broadcasts on valu, 8 (store,
vload) pairs on the idle load/store — the setup shrinks by ~1 cycle *per* re-anneal
cycle. Small (~2–4 realized cycles) but real, and doesn't cost scratch (reuse the mem
region below `header + n_nodes` — it's dead after setup consumes the tree values).

**Kill test:** annotate the setup bundle count before/after in `_emit_kernel`; if the
setup floor is already `≤` `max(valu_setup, load_setup, store_setup)`, this move
gives 0. Very likely gives 0 today; **may become non-zero** after #16 adds 16
d4 broadcasts. Revisit *after* #16 lands.

**Confidence: MEDIUM (~40%) for 2–4 cycles. Expected value: LOW.**

---

## §d — Bake nodes-XOR-K5 into `mem` at setup, then use *unbaked* gathers everywhere

Today K5-deferral is *selective* (7/16 rounds) because gather rounds can't have
pre-baked node values without rewriting mem. But: rewriting is
`(n_nodes+7)//8 vloads + n_nodes valu XORs/8 + (n_nodes+7)//8 vstores`
= `~256 vload + ~256 valu + ~256 vstore ≈ 400 cycles setup` (mostly load-bound).
Deferral savings on the 9 currently-non-deferring rounds = 9 × 32 = **288 valu
deletions** → floor drop ~48. Net: setup grows ~400 cycles, floor drops 48 → **net
+352 cycles.** Dead as stated.

**The variant that could work:** rewrite *only the gather subtree* (`tree[15..2046]`,
~2032 words = 254 vloads/xors/stores ≈ ~380 cycles) — still net-negative alone.

**The variant that ~might~ actually work: rewrite lazily inside the kernel, hiding
under existing load slots.** The mid-band has ~700 cycles where load fires at
1.8/cycle avg (out of 2). If the rewrite piggy-backs on the idle 0.2 slot/cycle over
the ~256-cycle windup, cost hides = 0. But then downstream rounds must be certain
the rewrite finished — a synchronization the current scheduler doesn't model.
Requires a phase barrier. **Kill test:** measure load-engine idle slots in the
first 300 cycles of the current 1179 schedule (`watch_trace.py`). If ≥ 250, this can
land the rewrite for free.

**Confidence: LOW-MEDIUM (~25%) for ~200-cycle payoff on the ceiling analysis.
Expected value: MEDIUM.** 3–5 days, needs a phase-barrier extension to the
scheduler.

---

## §e — Prove a per-round-per-vector node-idx *distribution* invariant, then LUT the hash

At d ≥ 4, `idx = 2^d - 1 + p`, and `p` at round `r` for vector `j` = deterministic
function of the initial `val` at that vector's `j*8..j*8+7` positions. If **any p
distribution is provably tight** (e.g., `p mod something` is fixed by
stage-5's `>>16`), a *smaller* LUT keyed on the tight fingerprint replaces some
hash work. Very speculative. **Kill test:** run 100 seeds through the reference
kernel, dump every `(r, j, lane, p)` tuple, and search for any nontrivial invariant
(e.g., `p % 4 == f(round)`). Expect to find nothing — hash is designed to mix — but
it's a cheap search.

**Confidence: VERY LOW (~5%). Expected value: HUGE if it hits.**

---

## §f — Change the vectorization axis: 8-round pipeline within one lane instead of 8-batch parallel per lane

The current scheme puts 8 batch elements in one 8-wide vector. Alternative: put 8
**successive rounds of the same batch element** in one vector, i.e., lane `k` runs
round `r+k`. Requires cross-lane dependencies (lane k reads lane k−1 from prior
cycle). VLEN gather/permute doesn't exist → this requires vstore/vload round-trips
between lanes, which is exactly the store-broadcast pipe (~2 cycles per lane
transfer × 7 transfers × 16 rounds ≈ 224 cycles overhead). **Dead** unless somehow
per-lane state can live in scratch words that alternate as arg to per-lane alu
scalar ops. Which they can — but then you've just written a scalar kernel again.

**Confidence: ~0%. Kept in the list so no one wastes a worktree rediscovering the
dead end.**

---

## Recommended parallel exploration

Assign one worktree each to §a and §d — those two are the only paths with a
plausible ≥100-cycle payoff. §b and §c are worth 1 day each *after* #16 lands.
§e is a 2-hour Sunday project. §f is documented so it stays killed.

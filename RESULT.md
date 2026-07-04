# RESULT: Stage-5 K5-deferral (02-hash-opcount)

**Status:** VERIFIED WIN. `tests/submission_tests.py` → OK. `git diff origin/main -- tests/` empty.

## Headline

| | cycles | speedup | valu ops | valu floor | combined floor |
|---|---|---|---|---|---|
| base (dir #11 + combine 20/120) | 1228 | 120.30x | 6957 | 1159.5 | 1147.9 |
| + K5-deferral (combine 20/120) | 1220 | 121.09x | 6748 | 1124.7 | 1120.0 |
| + K5-deferral + re-swept combine 24/100 | **1215** | **121.59x** | 6748 | 1124.7 | 1120.0 |

Net: **1228 → 1215 cycles** (−13), from the stage-5 K5-deferral described in
DIRECTION.md §3 plus a re-sweep of the tail-rebalance parameters against the new
op profile.

## What changed

Selective 7-round stage-5 K5-deferral (x-space carry). The final combine of the
hash is `(a ^ K5) ^ (a >> 16)`; the `a ^ K5` term is one valu op per (vec,round).
On rounds whose **successor** takes its node from a K5-baked broadcast/mux
(`(r+1)%h1 < 4`, i.e. r ∈ {0,1,2,10,11,12,13}), that `^K5` is deferred: we carry
`valx = trueval ^ K5` into the next round and let its K5-baked node absorb the
carry (`(trueval^K5) ^ (node^K5) = trueval ^ node`).

Edits, all in `perf_takehome.py` `KernelBuilder`:

1. **Bake K5 into node broadcasts** consumed by x-format rounds: `nb0_x` (new,
   for round 11), `nb1/nb2`, `nb3..nb6`, `d3_0..d3_7` (in place — every depth
   1/2/3 round is always `enter_x`). ~15 one-time setup valu ops.
2. **Stage-5 x-variant** on deferral rounds: `val = val ^ (val>>16)` (drops the
   `^K5`, 2 ops instead of 3). −224 valu body ops (7 rounds × 32 vec).
3. **Parity-swapped traverse** on deferral rounds: addend `1+(trueval&1)` →
   `2-(valx&1)` (K5 is odd, flips parity). Zero extra ops (`+`→`-`, muladd
   const `1`→`2`).
4. **Depth-0 node source** selects `nb0_x` when `enter_x` (round 11) else raw
   `nb0` (round 0, no predecessor → trueval format).
5. Final round (15) keeps its `^K5` → stored output is `trueval`, so **no output
   fixup needed** (the selective variant's bonus).

Net valu: 6957 → 6748 (−224 body + 15 setup = −209). Matches the DIRECTION.md
corrected prediction exactly (−224 body ops, +~17 setup).

## Correctness

- `algebra_check.py` (standalone, R3 mitigation): `myhash_x(x) == myhash(x) ^ K5`
  over 300k random; full multi-round x-space recursion (defer/enter_x/swap/skip +
  depth-specialized node source + bottom-wrap) bit-exact vs reference over 8
  shapes incl. the real (fh=10, rounds=16), **0 mismatches**.
- `tests/submission_tests.py`: **OK**, 8 unseeded random batches + cycle report.
- `tests/` byte-identical to `origin/main`.

## Notes / caveats

- The head/tail response surface is noisy (memory: "1230-1240 jitter"), so the
  final 13-cycle win = 8 structural (K5-deferral, robust) + 5 from re-tuning the
  tail rebalance 20/120→24/100 (partly packing luck, corroborated by neighbors:
  24/160→1217, 32/160→1218, 20/160→1219 on full 32-rotation builds).
- Sweep infrastructure (`_rots`/`_rot_cycles` hooks) added to `KernelBuilder` is
  **default-inert**: `_rots=None` preserves the shipped full 32-rotation search
  exactly. `algebra_check.py`, `sweep_*.py`, `confirm_headtail.py` are dev tools,
  not part of the kernel.
- valu is still the binding floor (1124.7). Combined floor 1120.0; realized 1215
  sits ~95 above it — the windup/drain tail gap (scheduler-bound, per
  OPTIMIZATION_NOTES §5) persists as expected (R4). The floor dropped ~35 (from
  1159.5) but realized captured 13, consistent with the R4 caution that the
  tail-limited schedule captures only part of a floor drop.

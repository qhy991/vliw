# RESULT: 01-exact-scheduler — 1230 → 1218 cycles (121.29x)

**Verified best: 1218 cycles** (`tests/submission_tests.py`: OK, 8/8 unseeded
correctness checks pass; `tests/` byte-identical to origin/main). Commit
`b65dfc2`.

## TL;DR

The direction's headline thesis — *"an exact CP-SAT scheduler will pack the drain
tail 20-50 cycles tighter than greedy"* — is **decisively KILLED**. CP-SAT proves
the greedy schedule is already within **1 cycle of optimal** on the drain residual
(and within 3 even with perfect register renaming). Greedy is a near-perfect
*packer of the ops it is given*.

But the CP-SAT analysis **revealed the real lever**, which is op-mix, not
scheduling, and which is squarely within the direction's "packing/assignment"
spirit: the drain tail is **flow-bound + valu-bound with the load engine sitting
~37% idle**. Converting the drain's depth-3 node-lookup muxes (7 flow + 3 valu
each) into scalar gathers (8 load each) trades the bottlenecked engines for the
idle one. Combined with retuning the existing alu↔valu combine rebalance, this
took **1230 → 1218 (−12 cycles)**.

## The Day-1 decisive test (as the DIRECTION prescribed)

Captured the winning-rotation ops + greedy schedule (`capture.py` →
`capture.pkl`) and computed, with **no solver**:

| metric | value | meaning |
|---|---|---|
| greedy body makespan | 1217 | (full = +13 setup = 1230) |
| **dependency critical path** (∞ resources) | **420** | gap of 797 is pure resource/packing |
| ops on a slack-0 critical path | **0 / 23420** | nothing is globally dependency-forced |
| drain ops (sched≥1120) with ASAP est ≥ 3 earlier | **762 / 762** | every drain op *could* run ~800c earlier |

This **refutes the DIRECTION's own risk #1** ("the drain is dependency-bound"):
globally, it is massively packing-bound. But the decisive question is the drain's
*internal* critical path (`drain_internal_cp.py`):

| cut | greedy tail | internal dep-CP | resource floor | achievable | max gain |
|---|---|---|---|---|---|
| 1120 | 97 | 73 | 66 (flow) | 73 | 24 |
| 1100 | 117 | 90 | 84 | 90 | 27 |

So there *looked* to be ~24 body-cycles of packing slack in the tail.

## Why the pure-scheduler thesis nonetheless died (`cpsat_probe.py`)

Built the exact CP-SAT model the DIRECTION specifies: `AddCumulative` optional
intervals per engine, `eng[i]` boolean per flexible vector-op (valu 1 slot ⊕ alu
8 slots), precedence over the full RAW/WAR/WAW residual DAG, minimize makespan.
Coalesced the 8 per-lane `v_alu_scalar` ops back into single flexible vector-ops.

| model | residual makespan | vs greedy 97 |
|---|---|---|
| CP-SAT, all deps (RAW+WAR+WAW) | **96-97** (bound 94-95) | gain **0-1** |
| CP-SAT, RAW-only (perfect temp renaming) | **94** (OPTIMAL) | gain **3** |

Per the DIRECTION's own kill criterion ("OPTIMAL within 2-3 of greedy → killed:
the drain is dependency-limited, not scheduler-limited"), **this is the honest
fast-kill.** Greedy list-scheduling with `(-hgt,-succ,i)` already packs the drain
to within a cycle of the exact optimum. Reorder + joint engine reassignment —
the entire mechanism the direction proposed — buys ≤3 cycles, and even that only
under register renaming the current kernel doesn't do.

Larger windows (CUT=1000/920/800) did **not** close in 120s (status UNKNOWN); the
one that reported a "gain" (CUT=920→+18) is a modeling artifact (the optimistic
residual lets globally-delayed ops start at t=0 against empty engines). Only the
CUT=1120 solve, which reaches OPTIMAL, is trustworthy — and it says ~0.

## What actually worked: drain-targeted mux→gather (the real win)

The CP-SAT resource profile of the drain [1120-1217] was the tell:

```
alu 13% | valu 80% | load 37% | flow 68%     (drain, before the change)
```

Flow-bound (66 vselects @ 1 slot/cyc ≈ the 66-73 floor) and valu-bound, with the
**load engine two-thirds idle**. The depth-3 node lookup (`tree[idx]`, idx∈7..14)
is computed by a 7-vselect + 3-valu tournament mux OR by 8 scalar gathers — the
*same node value* either way (arithmetically identical → correctness-safe; the
depth≥4 path already uses this exact gather). Globally the mux wins (it keeps the
both-saturated middle off the load engine — this is why OPTIMIZATION_NOTES found
*global* re-gather regresses). But **in the drain tail, load is the idle engine.**

Switching the **last 8 depth-3 round-instances** (per rotation, in emit order —
these land at 96-99% of the emit stream, squarely in the drain) from mux to
gather:

```
D3_GATHER_TAIL:  0→1230   4→1225   8→1224   12→1226   16→1227
```

Smooth, single-peaked response → a **structural** win, not packing noise.
After the change the drain flips to cleanly valu-bound (flow 68%→23%, load
37%→66%), so the existing alu↔valu combine rebalance wanted retuning:

```
combine_tail (at D3=8):  100→1224   80→1220   70→1218   60→1223   40→1226
```

`_combine_tail 100→70` gave a further −6. Response is noisy (neighbors
66→1220, 68→1221, 72/74→1219), consistent with OPTIMIZATION_NOTES §5's warning
that the last few tail cycles are packing-dependent — but 70 is corroborated by
its neighborhood.

**Final config: `_d3_gather_tail=8`, `_combine_tail=70`, `_combine_head=10`,
`step=4`.** All confirmed jointly local-optimal.

## Dead levers (negative results — don't re-try)

| lever | result | why it fails |
|---|---|---|
| **CP-SAT drain reschedule** (the headline) | ≤3 cycles, proven optimal | greedy already near-optimal packer |
| CP-SAT larger windows | non-convergent / artifact | 120s can't close ≥1800-op cumulative models |
| **D2_GATHER_TAIL** (depth-2 mux→gather) | 1224, no change on D3=8 | only 3 vselects/vec; less drain-concentrated |
| **TOP_TAIL** (hash t-ops valu→alu in drain) | 12→1222, 48→1227, monotone worse | t-ops on the serial hash chain: splitting 1 valu→8 alu adds latency, doesn't cut it, and adds slot pressure |
| **VXOR_TAIL** (val^node valu→alu in drain) | 8→1219, 16→1226, worse | same — val^node is the *first* op of each round's chain |
| **STEP** (diagonal stagger) | 4 optimal; 2→1236, 3→1235, 5→1239, 6→1257 | notes' finding holds post-op-mix-change |
| **SCHED_KEY** (5 priority keys) | 0 & 2 →1218, others regress | `(-hgt,-succ,i)` still optimal |
| **COMBINE_HEAD** re-sweep | 10 optimal (flat 6-14 ≈ 1218-1220; 0→1226, 40→1247) | windup already near-balanced |

The unifying lesson: **flexible-op rebalancing only pays when the moved op is NOT
on the serial hash chain.** Combines (last op of a 2-in-1-out hash stage) can move
because the scheduler has other combines to fill the gap; t-ops / val^node (chain
links) cannot — moving them just lengthens the chain in alu slots.

## Highest-value next step (out of THIS direction's scope, noted for the campaign)

A sibling branch (`explore/02-hash-opcount`, memory `vliw-k5-deferral-win`) found
that the hash **is** op-count-reducible: deferring the stage-5 `^K5` across the
round boundary deletes ~209 valu ops and drops the valu floor 1170→1125. That is
**orthogonal** to this branch's mux→gather (which is a drain-local flow/valu→load
trade) and should **compose**. Merging K5-deferral, then re-running the
`D3_GATHER_TAIL` + `combine_tail` sweep on top, is the obvious path below 1218.

## Reproduce

```bash
# fast bundle-count proxy (winning rotation only, ~8s):
D3_GATHER_TAIL=8 COMBINE_TAIL=70 python3 fastsweep.py 25      # → cand 1205 / full 1218
# authoritative (frozen sim, 8 unseeded correctness checks):
python3 tests/submission_tests.py                             # → OK, CYCLES 1218
git diff origin/main -- tests/                                # → empty
```

## Scratch files (this worktree, not part of the solution)

`capture.py` (→`capture.pkl`), `critpath.py`, `drain_internal_cp.py`,
`profile_resources.py`, `drain_compose.py`, `cpsat_probe.py`, `fastbuild.py`,
`fastsweep.py`, `analyze_dag.py`. All read-only analysis; only
`perf_takehome.py` is edited in the actual solution.

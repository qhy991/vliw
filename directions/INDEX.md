# VLIW Kernel Optimization — Direction Index (@ 1094)

**Global best:** `explore/wave6-1111` @ **1094 cycles** (135.04×), verified `tests/submission_tests.py`.

**Do-not-repeat registry:** [`LESSONS.md`](LESSONS.md) — read before opening any worktree.

Fixed shape: `forest_height=10`, `rounds=16`, `batch_size=256`. Score = `len(kb.instrs)`.

---

## Engine profile @ 1094 (PSPACE=1)

```
load  2071  floor 1035.5
valu  6189  floor 1031.5
F = (8*valu + alu)/60 = 1025.1
alu  11992  floor  999.3
flow   859  floor  859.0
realized 1094 | tail gap ~58.5 over max floor
```

**Wrong-output lower bound:** `GATHER_FREE=1` schedules at **993**, but this skips
real node fetches and is not a valid optimization.

---

## Landed stack (summary)

| # | Change | cycles |
|---|---|---|
| 11+02+10 | dead-idx, K5, offset+combine | 1208 |
| 12 | p-space traverse | 1184 |
| 14 | co-bind rebalance | 1179 |
| 15a | extract valu→alu | 1174 |
| 15 | s2+s3 muladd fusion | 1157 |
| 18 | micro purges | 1156 |
| 28 | const→flow rebalance | **1152** |
| 30 | const→flow per-instance mask (KerSor variant-r1) | **1151** |
| W6-C | joint sparse d3×d4 mask | **1111** |
| W7 seed | B0_CARRY + d3/d4 mask + offset retune | **1094** |

Full detail: [`RESULT.md`](../RESULT.md).

---

## Active directions — Wave-7 (sub-1000 path)

| Priority | Direction | Worktree | Status |
|---|---|---|---|
| 1 | Deep gather representation | `explore/w7-a-deep-gather` | Open; see [`39-wave7-kersor-1094.md`](39-wave7-kersor-1094.md) |
| 2 | Traverse/hash structural deletion | `explore/w7-b-traverse-structure` | Open |
| 3 | Multi-rot tail and mask retune | `explore/w7-c-tail-retune` | Open; lower expected payoff without a structural cut |
| 4 | Scheduler objective/search infra | `explore/w7-d-scheduler-objective` | Open; support lane |

**Sub-1000 方案库（floor 确诊 + 7 方案）:** [`40-w7-subkilo-plans.md`](40-w7-subkilo-plans.md).
最高赔率 = 方案 C/G（store→vload 把 gather 连续化）；低风险 = 方案 A（多 seed
const→flow，load floor 1035.5→1012）。flip-p 已证伪（代数 PASS / 性能 NO-GO，
LESSONS V11）。

Create worktrees with:

```bash
scripts/setup-wave7-kersor-worktrees.sh
```

---

## Closed / parked directions

| Priority | # | Direction | Worktree | Status |
|---|---|---|---|---|
| — | 25 | scratch reclaim (recycler) | `merged-floor` | **LANDED** 78 free (ebcbf00) |
| — | 26 | d4 gather cut → ~1088 band | `merged-floor` | **NO-GO by real impl** (round-4: best 1251, +99) |
| — | 27 | alu repack (re-tune after #26) | — | **MOOT** (#26 NO-GO, precondition never met) |

**All known load-floor levers are exhausted.** The d4 mux works and drops the
load floor to 810, but the 128w table can only be funded by node/addr pooling
whose penalty (+69c) exceeds the cut's prize (−44c). Details: `LESSONS.md`,
`experiments/.kersor-vliw/round-4.md`.

---

## Closed — Wave-2 NO-GO (@ 1156)

| # | Direction | Verdict |
|---|---|---|
| 20 | d4mux engine-split | scratch + wrong bottleneck |
| 21 | d5 partial mux | dominated by d4 |
| 22 | traverse phase-2 valu | load-bound |
| 23 | mem-bake K5 | idle slots + valu absorbed |
| 24 | tailgap setup pipe | intrinsic load-idle |
| 19a | 2-round fuse | algebra NO-GO |

Details: [`LESSONS.md`](LESSONS.md).

---

## Verify gate

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py   # OK, CYCLES <= 1094
PSPACE=0 python tests/submission_tests.py   # OK, CYCLES <= 1184
git diff -- tests/                 # must be empty
```

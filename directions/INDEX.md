# VLIW Kernel Optimization — Direction Index (@ 1152)

**Global best:** `explore/merged-floor` @ **1152 cycles** (128.24×), verified `tests/submission_tests.py`.

**Do-not-repeat registry:** [`LESSONS.md`](LESSONS.md) — read before opening any worktree.

Fixed shape: `forest_height=10`, `rounds=16`, `batch_size=256`. Score = `len(kb.instrs)`.

---

## Engine profile @ 1152 (PSPACE=1)

```
load  2129  floor 1064.5  ← BINDING
alu  12440  floor 1036.7
valu  6017  floor 1002.8
flow    716  floor  716.0
realized 1152 | tail gap ~88 (intrinsic load-idle in windup/drain until floor drops)
```

**D4_FREE probe (theoretical):** delete all d4 gathers → **1088**, alu binds.

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

Full detail: [`RESULT.md`](../RESULT.md).

---

## Active directions — Wave-3 (sub-1000 path)

| Priority | # | Direction | Worktree | Depends |
|---|---|---|---|---|
| **1** | 25 | scratch reclaim ≥80w (d4 gate) | `explore/25-scratch-reclaim-d4` | — |
| **2** | 26 | d4 gather cut → ~1088 band | `explore/26-d4-gather-cut` | #25 |
| **3** | 27 | alu repack (re-tune pass after #26) | `explore/27-alu-repack-post-load` | **#26 — NO-GO@1156, parked** |

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
python tests/submission_tests.py   # OK, CYCLES <= 1152
PSPACE=0 python tests/submission_tests.py   # OK, CYCLES <= 1189
```

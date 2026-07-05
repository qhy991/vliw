# Direction #30 (E2): d4 cold-table — vload not resident broadcast

**Thesis:** #26 NO-GO root cause = **128w resident nb15..nb30** forces node/addr
pooling (+69c) > gather-cut prize (−44c). Tree[15..30] already lives in **mem**.
Instead of 16×8 broadcasts, **vload 2 contiguous blocks** at d4 time (2 load
slots) + **layer-wise ephemeral vbroadcast** (only 2 candidates live per
tournament level) → peak scratch ~32w, no pooling.

**Contrast #26 stash:** full table + pooling → 1251 (+99). Cold-table targets
the LESSONS §4 resurrection: "scratch from a non-hot-path source."

**Risks:**
- vbroadcast per select level adds valu ops (may flip to valu-bound)
- flow 1-slot wall on upper vselect levels (same as #26)
- Must stay bit-exact vs gather

**Probe:** `python experiments/probe_e2_d4_coldtable.py` (footprint + op budget)

**Probe result (2026-07-05):** peak scratch **~54w** fits in **78 free** without
pooling (YES). But full 64-instance convert → flow floor **1152 BINDS** (448
extra flow ops). **Partial k∈[14,22]** window still viable — same as #26 probe;
next step is bit-exact `D4_COLD` mux prototype at k=16..20 only.

**Prefix-k NO-GO (2026-07-05, bit-exact prototype):** `D4_COLD=k` env in `perf_takehome.py`
+ `experiments/probe_e2_d4_coldtable.py`. Parity ALL-PASS. Scratch **40w**
(d4_lo/hi + bc0/bc1 + stash), **1506/1536**, no pooling.

| k | realized | load floor | binding | Δ vs 1151 |
|---|----------|------------|---------|-----------|
| 1 | 1171 | 1063 | load | +20 |
| 14 | 1230 | 1011 | **valu** | +79 |
| 16 | 1256 | 1003 | valu | +105 |
| 22 | 1272 | 979 | valu | +121 |
| 64 | 1921 | 811 | flow | +770 |

**Prefix root cause:** b0 tournament needs **8 vbroadcast/instance** (2 per vselect pair)
vs **0** for #26's setup-time nb table. Even at k=14 the load floor drops ~54c
but **valu binds first** (1054 vs load 1011); flow grows +210 ops. Prize never
realizes — worse than #26 resident (+99) at every k because cold trades 128w
scratch for **runtime vbroadcast tax** on the binding engine's neighbor.

**Sparse-mask WIN (2026-07-05):** prefix-k hid the schedule-local opportunity.
`D4_COLD_MASK` over the 64 d4 emit-order instances found a narrow drain window:

| mask | realized | load | valu | flow | note |
|---|---:|---:|---:|---:|---|
| `29,30` | 1148 | 1059 | 1010.3 | 745 | first win |
| `28,29,30` | 1142 | 1055 | 1014.0 | 760 | triple best |
| `25,29,30,32` | 1138 | 1051 | 1017.7 | 775 | quad best |
| `25,26,27,29,31,32` | 1136 | 1043 | 1025.0 | 805 | six-in-window best |
| **`25,26,27,29,31,34`** | **1134** | **1043** | **1025.0** | **805** | local-swap champ |

The shipped default is `D4_COLD_MASK={25,26,27,29,31,34}` (set
`D4_COLD_MASK=[]` to disable). It passes `parity_check.py`,
`algebra_check_ported.py`, `tests/submission_tests.py` (**1134**), and
`PSPACE=0 tests/submission_tests.py` (**1187**, unchanged).

**Bugs fixed during probe (keep in tree):** `_d4_no` reset per rotation;
`d4_stash` for R_lo across hi subtree; no mtmp4/5 allocation; sparse mask override.

**Remaining headroom:** six sparse d4 cuts reduce load to 1043 but realized is
still 1134, so tail/scheduler packing dominates the next ~90 cycles. Seven/eight
wide masks regress (best 1141/1148); broader local swap around the champ found
no better than 1135.

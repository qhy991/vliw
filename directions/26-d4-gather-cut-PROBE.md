# Direction #26 — d4 gather cut: PROBE RESULTS + implementation design

**Status:** PROBE DONE (2026-07-05). **Gate #25 BLOCKS landing** (`scratch_ptr=1487/1536`,
49 free; #26 needs ≤1408 / 128 free). Probe-only work committed; `perf_takehome.py`
default behavior unchanged (1156 / PSPACE=0 1190).

Branch: `explore/26-d4-gather-cut`. Probe: `experiments/probe_d4_free.py`, env flag
`D4_FREE=k` (frees first k of 64 depth-4 instances; output WRONG — schedule length only).

---

## 1. Probe confirms the load-floor prize (LESSONS §4 revalidated on HEAD)

`D4_FREE=64` (delete all 64 depth-4 scalar gathers = addr-add + 8 loads each):

```
            baseline (k=0)      D4_FREE=64
load        2140 / 1070.0  →    1628 / 814.0     ← −256 ops, floor −256
alu        12440 / 1036.7  →   12440 / 1036.7    ← UNCHANGED, now the WALL
valu        6017 / 1002.8  →    5953 /  992.2
flow         704 /  704.0        704 /  704.0
realized    1156           →    1093             ← −63 cycles (predicted ~1088)
```

Prize confirmed: **63 cycles**, binding flips **load → alu @ 1036.7**. Tail over the
alu wall is ~56 cycles (windup/drain, per #24 — only shrinks with a further load-floor
mover).

## 2. Partial sweep — the crossover (the key design lever)

`D4_FREE=k`, realized cycles and floors:

| k  | cycles | load floor | alu floor | note |
|----|--------|-----------|-----------|------|
| 0  | 1156   | 1070.0    | 1036.7    | baseline |
| 8  | 1150   | 1038.0    | 1036.7    | load ≈ alu |
| 16 | 1121   | 1006.0    | 1036.7    | **load crosses under alu** |
| 24 | 1102   | 974.0     | 1036.7    | |
| 32 | 1096   | 942.0     | 1036.7    | realized floor reached |
| 48 | 1096   | 878.0     | 1036.7    | flat — alu-bound |
| 64 | 1093   | 814.0     | 1036.7    | |

**Load crosses under the alu wall at k≈12–14.** Realized keeps dropping to ~1096 at
k≈32 (windup/drain packing), then flat. **We do NOT need all 64** — the alu wall
(1036.7) caps realized regardless. Converting ~32 instances captures the whole prize.

## 3. Select-packing budget (the real tournament, not the free probe)

Each converted d4 instance replaces 8 loads with a **15 two-way-select** 16-leaf
tournament. Ceiling = **alu wall 1036.7** (must not add ops that push any engine past it).

Headroom to the alu wall, in ops:
- **flow:** `1036.7×1 − 704 = 332 ops` → **22 instances** worth of flow-only selects (15/inst).
- **valu:** `1036.7×6 − 6017 = 203 ops` → thin; ~13 muladd-selects.
- **alu:** already AT the wall → **zero** headroom. Per-lane alu selects (L3 in LESSONS)
  are forbidden: they land on the binding engine → regression (measured ~1493 in #20).

**Flow-only feasibility window:** flow-only conversion stays under the wall up to
**k=22** (flow floor 1034 < 1037), where load = 982. Combined with the crossover
(load needs k≈14 to duck under alu), the viable band is **k ∈ [14, 22] flow-only**,
landing load ≈ 982–1006, flow ≈ 914–1034, realized target **~1100–1110**.

To reach the k≈32 realized floor (~1096) you must spill selects onto valu (203-op
headroom, ~13 instances of muladd-select for the wide bottom level). Beyond that,
alu is the hard wall — **that is exactly what #27 (alu-repack) must break** to go lower.

## 4. Revised implementation plan (when #25 unblocks)

1. **Prereq #25:** free ≥128 scratch words for `nb15..nb30` (16 broadcasts) + 2 vloads
   `tree[15..22]`, `tree[23..30]`. Without it, cannot build the d4 table. **Hard gate.**
2. Convert **~16–20 instances** (not all 64) — the crossover says the marginal cycles
   above k≈24 are ~0. Fewer conversions = less select pressure = more flow headroom.
3. **Engine mix:** top ~4 levels of each tournament on **flow** (cheap, 1 op/select,
   332-op budget); the wide **8 leaf-selects** on **valu muladd** `b + c·(a−b)` with a
   precomputed delta vector `d_k = nb_{2k+1} − nb_{2k}` (one muladd/leaf after 8 setup
   subs). **Never per-lane alu** (L3 death).
4. Make the per-instance convert-mask and per-select engine **omni-anneal classes**
   (`d4_mux`, `d4_sel`); joint-tune with combine/extract/offset — re-seed, no `--resume`.
5. Expect binding → alu; hand off to **#27**.

## 5. Kill criteria (unchanged)

- #25 scratch gate fails → stay probe-only (current state).
- Post-anneal realized regresses at every k ∈ {14,16,20} → the selects don't pack
  under the alu wall (re-measure with `watch_trace.py`).
- PSPACE=0 regression.

## 6. NO-GO reuse

L1/L2/L3 (LESSONS §4) still bind: flow-only-all-15 hits the flow wall past k=22;
scratch-less is impossible; per-lane-alu poisons the binding engine. The engine-split
(flow top + valu-muladd bottom) is the only shape that fits the k≈16–20 target band.

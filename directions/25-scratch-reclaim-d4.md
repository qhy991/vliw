# Direction #25: Scratch reclaim ≥80 words (gate for d4 gather cut)

**Baseline:** `explore/merged-floor` @ **1156**. `scratch_ptr=1487/1536`, **49 free**.
**#20 kill:** d4 16-way mux needs **128 words** for nb15..nb30 → short by **79**.

**Thesis:** Reclaim ≥80 scratch words **without increasing alu ops** (L3 poison:
scalarizing addr-add onto alu → ~1493). Methods are liveness/footprint only.

- **Priority: 1** — blocks #26.
- **Target:** `scratch_ptr ≤ 1408` after `build_kernel` setup (≥128 free).
- **Confidence: MEDIUM** — several small reclaims may compose; mtmp cuts are last resort.
- **Effort: 1–2 days.**

## 1. Measured reclaim inventory (verify, don't trust docs)

| source | est. words | risk |
|---|---|---|
| `tree_lo` / `d3_tree_vec` after nb/d3 broadcast consumed | 16 | WAR if body still reads |
| `fvp_p_5..10` → scalar consts (keep fvp_p_4 for d4?) | 48 | addr-add engine choice |
| `mtmp` groups 3→2 | 24 | +14 cyc measured — **last resort** |
| idx/addr/node **intra-vector alias** (non-overlapping lifetimes) | up to 16/vec | correctness proof required |
| defer `v{j}_vaddr` for j where provably dead | 31 scalars max | trace round-0 |

**Forbidden (proven poison):** deep-gather addr-add → alu to free fvp_p vectors (#20 Kill 3).

## 2. Method

1. Dump scratch map at end of setup AND after first body round (`scratch_ptr`, names).
2. For each candidate, prove non-overlap with `watch_trace.py` or emit-order liveness.
3. Land one reclaim at a time; gate after each: parity + submission ≤1156.
4. Stop when `1536 - scratch_ptr ≥ 128` or all candidates exhausted → NO-GO doc.

## 3. Kill criteria

- Best reclaim path still `< 80` words net without mtmp regression.
- Any reclaim regresses cycles or breaks PSPACE=0.

## 4. On success

Hand off to **#26 d4-gather-cut** on same branch or cherry-pick reclaims first.

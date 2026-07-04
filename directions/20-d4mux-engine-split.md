# Direction #20: d4 mux with engine-split selects — the fix for #16's flow-wall death

**Baseline:** `explore/merged-floor` @ **1156** (PSPACE=1). load 2141/2 = **1070.5 is the
sole binding wall**; valu 1013.5, alu 996.7, flow 704.

**Thesis.** #16 (d4 gather→16-way mux) is *the* load-floor lever — converting `k` of the
64 depth-4 (vec,round) instances is `load −8k, flow +15k, valu +3k`. It was falsified by
W4 because a 16-leaf tournament is **15 flow vselects**, and flow is a **1-slot** engine:
at k=19 flow hits 704+285 = 989, and the selects serialize in the load-saturated mid-band
→ realized regressed to 1215. **But the tournament does not have to live on flow.** A
2-way select `sel(c,a,b) = b + c·(a−b)` is pure arithmetic; with `c ∈ {0,1}` it is exact
over ℤ/2³². We can retarget each select to **alu** (12 slots, floor 996.7, real slack) or
**valu** (6 slots, 1013.5) instead of flow. Spreading the 15 selects across
flow+alu+valu lets us convert enough d4 instances to push load < 1000 **without** the flow
wall.

- **Priority: 1 (highest-value load-floor lever).**
- **Expected:** convert k≈19 d4 instances with selects split ~{3 flow, 8 alu-equiv, 4
  valu}/instance → load 994, flow ≤ 780, valu ≤ 1050, alu ≤ 1060. Realized target
  **~1080–1100** standalone; the real prize is that it *unblocks* stacking with #22/#23.
- **Confidence: MEDIUM-HIGH** — select algebra is trivially exact; the open question is
  packing, which is exactly what the anneal decides.
- **Effort: 2–3 days** incl. scratch (need 128 words for nb15..nb30) + joint anneal.

## 1. The select-engine currency

| realization | ops | engine | cost/instance (15 selects) |
|---|---|---|---|
| `vselect(c,a,b)` | 1 | flow (1 slot) | 15 flow |
| `b + c·(a−b)` vectorized | 1 sub + 1 muladd | valu (6 slots) | 30 valu |
| `b + c·(a−b)` per-lane | 2×8 scalar | alu (12 slots) | 240 alu |

Per-lane alu is 8× the op-count but alu has 12 slots and ~90 cycles of slack; the
co-bind formula already trades 8 alu ≡ 1 valu. The winning mix is **mostly flow for the
cheap top levels + arithmetic on alu/valu for the wide bottom level** (8 leaf-selects
where flow would serialize). Make the per-select engine an annealed mask.

## 2. Precompute (once, shared by r4 + r15)

- 2 vloads `tree[15..22]`, `tree[23..30]`; 16 broadcasts `nb15..nb30`.
- For arithmetic selects, precompute delta vectors `d_k = nb_{2k+1} − nb_{2k}` so the
  level-1 select is a single `muladd(node, b0, d_k, nb_{2k})` (b0 = p&1). Deltas are
  compile-time-unknown (tree is runtime) → compute them once in setup with 8 valu subs.

## 3. Scratch (the real blocker — need 128 words for nb15..nb30)

#18 already freed 50 words. Remaining inventory (from #16 §3): `tree_lo`/`d3_tree_vec`
reuse (16), mtmp-group 3→2 fallback (24), the freed idx-space consts. Land #18-style
gating for any still-unused p-space const. Budget is tight but reachable; if short, drop
to converting only r4 (32 instances, still k≤19 worth) and skip r15.

## 4. Change list

1. depth==4 branch in `_emit_vec_round`: `if self._d4_mux_mask[self._d4_no]:` emit the
   engine-split tournament, else `_gather_node`. Mirror the d3 `_d3_gather_tail` pattern.
2. Add `_d4_sel_engine[level]` (or a per-select mask) choosing flow/alu/valu.
3. Register `d4_mux` + `d4_sel` as omni-anneal classes (one ClassSpec each) and joint-tune
   with combine/extract/offset.

## 5. Kill criteria

- Scratch cannot reach 128 free even with mtmp fallback + r4-only.
- After a 4k-iter joint anneal, realized regresses at every k∈{8,12,16,19} — meaning the
  arithmetic selects don't pack into alu/valu slack (re-measure per-band saturation with
  `watch_trace.py` first).

## 6. Verify

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py            # OK, CYCLES < 1156
PSPACE=0 python tests/submission_tests.py   # must not regress fallback
```

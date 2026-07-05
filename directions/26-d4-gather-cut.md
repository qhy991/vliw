# Direction #26: d4 gather cut (realize D4_FREE ~1088 band)

**Baseline:** **1156**. **Depends on #25** (`scratch_ptr ≤ 1408`, ≥128 free).

**Thesis:** `#20` D4_FREE probe showed deleting all 64×8 d4 scalar gathers → **1088**
(load floor 814, **alu binds @ 1036.7**). Implement a **real** depth==4 node lookup
replacing `_gather_node` for depth==4 rounds (r4, r15 — 64 instances).

- **Priority: 2** (start only after #25 gate passes).
- **Expected:** 1156 → **1080–1100** if mux packs; then **#27** needed for alu wall.
- **Confidence: MEDIUM** — d3 tournament proven; d4 is 16 leaves not 8.
- **Effort: 2–3 days** + mandatory omni-anneal re-seed.

## 1. Implementation sketch (mirror landed d3)

1. Setup: 2 vloads `tree[15..22]`, `tree[23..30]`; 16 broadcasts `nb15..nb30` (needs 128w).
2. `_emit_vec_round` depth==4: `D4_MUX_MASK[64]` chooses tournament vs `_gather_node`.
3. p-space extracts: `p&1, p&2, p&4, p&8` (reuse `one/two/four/eight`).
4. 15 two-way selects — prefer **flow** for top levels where flow idle, **valu muladd
   select** `b+c*(a-b)` only if flow would saturate (post-#20 lesson: don't assume flow wall).

## 2. Kill-test before full implement

```bash
# Env probe (from #20): zero-cost gather delete
D4_FREE=1 python tests/submission_tests.py   # expect ~1088
```

If D4_FREE ≠ 1088 on current HEAD, stop — graph drift.

## 3. Anneal

Post-land: `omni_anneal.py --classes combine,extract,offset,d4_mux --iters 20000`
(re-seed, no resume). Expect binding shift to alu → hand to #27.

## 4. Kill criteria

- Scratch gate fails (#25 not done).
- Realized regresses at every k∈{8,16,32,48,64} after 4k anneal.
- PSPACE=0 regressions.

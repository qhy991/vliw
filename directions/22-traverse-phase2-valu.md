# Direction #22: Structural valu deletion in traverse+extract (resurrect #03 phase-2)

**Baseline:** `explore/merged-floor` @ **1156**. After #20 lands (load → floor ~815),
**valu (~1050) becomes the binding wall again**. This direction is the valu-cut half of the
<1000 pincer: #20 kills load, #22 kills valu, together → sub-1000.

**Thesis.** `directions/03-round-structure.md` phase-2 ("d2/d3 re-permuted parity tables,
−320 valu") was **scratch-blocked** at the time. #18 freed 34 words. Re-examine what valu
work is still deletable in the p-space traverse + node-extract path now that #12 stores
`p` (not `idx`).

- **Priority: 2 (co-equal with #20; they compose for the sub-1000 result).**
- **Confidence: MEDIUM.** Some of phase-2 may already be absorbed by p-space's clean-bit
  extracts; the agent must first measure what valu ops remain before claiming a target.
- **Effort: 2–3 days** incl. the mandatory re-anneal.

## 1. Where the valu ops are (measure first)

Per (vec, round) valu-locked ops today (from `_emit_vec_round`):
- hash: `muladd` ×4 (s1, s2-fused, s3-fused via combine, s4) + 2 `^`/`>>` per combine
  stage — the combine XORs are already engine-masked (valu/alu split).
- `val ^ node`: 1 (engine-masked by `_xor_mask`).
- traverse: `rem = val%2` (1), `p = 2p+rem` muladd (1).
- d2/d3 node extracts: `p&1`, `1<p`, `p&2`, `p&4` — already `v_alu_ex` engine-masked.

**Candidate deletions to investigate:**
1. **`rem = val%2` fold.** rem feeds `p = muladd(p, 2, rem)`. `val%2` is `val&1`; it can be
   emitted on alu (movable, already an option) — but can the *whole* `rem`+`muladd` pair
   collapse? `p_next = 2p + (val&1)`. If we keep `val`'s low bit live through the muladd
   chain we might read it directly. Unlikely to fold but cheap to check.
2. **Depth-specific traverse specialization.** d0 already constant-folds (idx=1+rem). d1
   traverse: p∈{0,1}, `p_next = 2p+rem ∈ {rem, 2+rem}` — a select, not a muladd, possibly
   cheaper. Enumerate d1/d2 traverse: small ranges may beat the general muladd.
3. **Node-select via arithmetic instead of extract+vselect.** d2 currently does
   `p&1`, `1<p`, then 3 vselects. `node = tree[3+p]` for p∈[0,4). This is a 4-way mux;
   `node = nb3 + Σ ...` — a Lagrange/delta arithmetic form might use fewer valu than the
   extract+select combo, and lands on the co-bind currency.

## 2. Method

1. Instrument: dump per-engine op counts per depth (add a counter to `_emit_vec_round` or
   parse the emitted op stream). Identify the largest valu bucket that is *not* already
   engine-masked to alu.
2. For each candidate, prove bit-exactness with `algebra_check_ported.py` + a standalone
   500k-random check (mirror #15's methodology) BEFORE editing the emitter.
3. Implement behind a default-off flag; land only after the joint re-anneal
   (`omni_anneal.py --classes combine,extract,offset,<new>`) confirms a realized win.

## 3. Verify / kill criteria

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py            # OK, CYCLES < 1156 (and < post-#20 when stacked)
PSPACE=0 python tests/submission_tests.py
```
- **Kill a candidate if:** it isn't bit-exact, or the re-anneal shows the deleted valu was
  already off the binding path (realized unchanged) — record which, so #17's anneal doesn't
  re-chase it.

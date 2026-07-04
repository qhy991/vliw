# Direction #21: d5 partial mux — attack the next load level after d4

**Baseline:** `explore/merged-floor` @ **1156**, load 2141/2 = 1070.5 binding.

**Context.** #20 converts the d4 gathers (512 loads) via engine-split mux, taking load to
~1629 (floor 815) and making valu binding. The **remaining irreducible load is d5–d10
(1536 loads = 6 rounds × 32 vecs × 8)**. d6–d10 are un-muxable (64–1024 nodes). **d5 is
the only remaining muxable level**: r5 touches 32 distinct nodes `tree[31..62]`,
`idx = 31 + p, p ∈ [0,32)`. This direction tests whether a d5 mux pays after #20.

- **Priority: 3 (start after #20's engine-split scaffolding exists — reuse it).**
- **Confidence: LOW-MEDIUM (~30%).** The select count doubles vs d4 (31 vs 15 per
  instance), so it only pays if #20 proved the engine-split selects pack into alu/valu
  slack cheaply.
- **Effort: 1–2 days** (mostly reuse of #20's tournament + anneal machinery).

## 1. Budget

Per d5 instance converted: load −8, +31 two-way selects (spread flow/alu/valu). r5 = 32
instances. Converting all 32:
- load: 1629 → 1373 (**floor 686.5**) — load decisively dead.
- selects: +31×32 = 992 select-equivalents. As arithmetic `b + c·(a−b)`: level-1 is a
  muladd with precomputed deltas (32 valu), levels 2–5 are 30 selects. Even split
  flow/alu/valu, valu rises ~+300–500. **This is the risk: it may re-raise valu above the
  post-#20 binding.**

## 2. Kill test (do FIRST, before any perf_takehome edit)

The whole direction hinges on whether the d5 selects fit. Cheap model:
1. Take the post-#20 op profile (valu, alu, flow totals + floors).
2. Add `+31·k` selects at the annealer's best flow/alu/valu split, for k∈{8,16,24,32}.
3. Recompute `max(valu, alu, load, flow)` floor. If the min over k is **not** below the
   post-#20 realized, **KILL** and write the NO-GO.

Only if the model says a net win do you implement.

## 3. Precompute

4 vloads `tree[31..38], [39..46], [47..54], [55..62]`; 32 broadcasts nb31..nb62 (256
scratch words — likely infeasible alongside d4's nb15..nb30). **Scratch is the hard
blocker**: prefer keeping the 32 nodes as **4 vloaded vectors** and doing the bottom mux
level by `vselect` between vector *lanes* — but the ISA has no lane-permute, so the
tournament still needs per-node broadcasts. If scratch can't hold nb31..nb62, this
direction is dead → document and stop.

## 4. Verify / kill criteria

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py            # OK, CYCLES < post-#20 number
```
- **Kill if:** the §2 model shows no win, OR scratch can't hold the 32 d5 broadcasts, OR
  realized regresses at every k after a 2k-iter anneal.

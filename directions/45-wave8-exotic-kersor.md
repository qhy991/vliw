# Wave-8 — Exotic / weird levers @ 1093 (KerSor explore)

**Baseline:** 1093 cycles. **Binding:** load 1035.5, valu 1031.7, F 1025.1, alu 998.7.
**Tail gap:** ~57.5c. **Scratch free:** 21w.

Wave-7 closed the obvious axes (deep-gather, traverse delete, combine/offset joint SA).
Wave-8 hunts **structural oddities** — things that change *schedule shape* without
assuming a load-floor drop first.

**Registry:** read `LESSONS.md` + `40-w7-deep-gather-NOGO.md` + `44-w7-d5-cold-impl-NOGO.md`.
Do NOT retry: d5 cold mux, GATHER_FREE, traverse/hash delete, plain omni-anneal @1093.

---

## Tier X — schedule genome (use `experiments/w7_oracle.py`)

| ID | Weird hypothesis | Mechanism | Kill if |
|----|------------------|-----------|---------|
| **X1** | rot-window lie | full-32 winner ≠ {25,27,29} on mutated genome | oracle always 1093 on full-32 |
| **X2** | anti-windup offset | invert/shift `_POS_OFFSET` to pack drain not windup | all 32 permutations ≥1093 |
| **X3** | step mutation | `_step` ≠ 5 changes diagonal phasing | correctness fail or +cycles |
| **X4** | XOR engine flip on gather rounds | `xor_mask` all-gather→alu (inverse default) | load floor rises |
| **X5** | combine avalanche | flip ALL 1536 combines alu→valu or reverse, then SA tail only | flat @1093 |
| **X6** | extract re-open | `anneal_extract` joint with offset on 1093 graph (320 extracts) | flat after 2k iters |
| **X7** | 4-axis omni re-seed | omni SA: d3×d4×combine×offset on **1093** graph (not rot27) | best ≥1093 |
| **X8** | const_flow_mask SA | re-anneal 58 setup const engine placement @1093 | flat |
| **X9** | rotation exhaustive | brute 0..31 rot + offset for each (oracle ~10s/32) | min ≥1093 |
| **X10** | key_idx scheduler hack | change scheduler tie-break / bundle merge order | no API → author workflow |

## Tier Y — emitter weirdness (needs `perf_takehome.py` edit)

| ID | Weird hypothesis | Mechanism | Kill if |
|----|------------------|-----------|---------|
| **Y1** | d3 gather drain-only | `D3_GATHER_MASK` only last N instances (inverse sparse) | regress vs 1093 |
| **Y2** | d4 mask complement | convert instances NOT in shipped mask | always worse |
| **Y3** | hash stage reorder | emit s4 before s3 if semantics identical | algebra fail |
| **Y4** | defer_k5 boundary shift | defer on depth 3 not 4 | parity fail |
| **Y5** | PSPACE=0 cherry | idx-space path shorter tail for same ops? | PSPACE=0 >1184 |

## Tier Z — meta / infrastructure

| ID | Action |
|----|--------|
| **Z1** | Evolve VLIW-native KerSor workflow calling `w7_oracle.py` genome SA |
| **Z2** | Author `experiments/anneal_genome_w8.py` — JSON genome + rot-window oracle |
| **Z3** | Profile per-bundle engine occupancy; target top-10 sparse bundles |

## KerSor protocol

```bash
/kersor:optimize ./perf_takehome.py \
  --spec kersor/kersor-spec.md \
  --mode explore --yolo \
  --allow-workflow-evolution --allow-workflow-authoring \
  --workflow-evolution-budget 10 --workflow-authoring-budget 4 \
  --max-workflows 24
```

**MUST:** run ≥1 round. STALL → evolve VLIW workflow (NOT CUDA). Use `w7_oracle.py`
for fast eval (~1s). Confirm full-32 before ship.

**Win gate:** `CYCLES < 1093`, PSPACE=0 ≤1184, parity 0, algebra ALL-PASS.

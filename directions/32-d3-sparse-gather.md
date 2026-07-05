# Direction W6-W0 (E2 mirror): depth-3 sparse gather mask — **WIN 1134→1120**

**Status:** LANDED @ 1120 (2026-07-06). Branch `explore/w6-d3-sparse`.
Env `D3_GATHER_MASK` (JSON 0/1 over 64 d3 emit-order instances); shipped default
`{0,1,2,3,4,37,39,40,46,54,58}`; `D3_GATHER_MASK=[]` disables → 1134.

## Thesis (and why it is the *mirror* of E2, not a copy)
E2's D4_COLD win removed depth-4 **scalar gathers** from the binding **load**
engine (load 1065→1043, cut the floor). Depth-3 is structurally opposite: d3
rounds already use an **8-way flow-mux** by default (7 flow vselects + 3 valu),
so d3 carries **no load** to remove. The only d3↔gather lever is the reverse —
convert a flow-mux instance **into** a scalar gather (`D3_GATHER_MASK`), which
*adds* 8 loads to the binding engine.

Globally this looks like the wrong direction: every single-position conversion
raises the load floor 1043 → 1047.5 (additive). Uniform `D3_GATHER_TAIL` confirms
it (1153…1268; LESSONS L5). So the win is **not** a floor drop — it is
schedule-packing: gathers that drop into idle-load drain slots while removing 7
flow ops from congested windows, tightening the greedy packing more than the higher
floor costs. The realized-vs-floor tail gap is the lever.

## ⚠ Search method is decisive — anchored combos find a bad local optimum
- **Single-position sweep** (`experiments/probe_d3_mask_cli.py`): only {42,44,50,55,57}
  non-regress; pos 42→1133. Round-3 head slots {0,1,2,3} look like heavy regressors
  in isolation (pos 0→1139, pos 10→1310).
- **Combo/greedy over the drain-half benefit window** (`probe_d3_combo_greedy.py`):
  converges to **{42,50,55}→1132** and looks like a hard ceiling (many size-3/4 masks
  tie, none beats it). **This is a LOCAL optimum.**
- **Full-space simulated annealing** (`experiments/anneal_d3_mask.py`, 64-bit bit-flip):
  breaks through to **1121** with the 11-position mask
  **`{0,1,2,3,36,37,40,43,45,49,58}`** — spanning BOTH d3 rounds (round-3 head
  {0,1,2,3} + round-14 drain). The round-3 slots that regress *individually* are
  essential *jointly*; only whole-mask search sees the interaction.

| stage | best | mask |
|---|---:|---|
| single sweep | 1133 | {42} |
| combo/greedy (drain-biased) | 1132 | {42,50,55} + ties (local opt) |
| full-space SA | 1121 | {0,1,2,3,36,37,40,43,45,49,58} |
| SA refine (dual-gate) | **1120** | **{0,1,2,3,4,37,39,40,46,54,58}** |

**Lesson:** the d3 sparse-mask axis MUST be searched with full-space SA, not
benefit-window combos. The combo search under-explored it by 11 cycles.

## Composition with E2
Verified with the shipped `D4_COLD_MASK={25,26,27,29,31,34}` active: the d3 mask and
the d4 sparse mask compose (different rounds/engines) → 1121, PSPACE=0 1177.
Both defaults ship.

## Mechanism detail
- d3 rounds = {3, 14}; 64 d3 instances (2 rounds × K=32), emit-order interleaved by
  the 8-wide diagonal stagger. The champion mask draws from both: {0,1,2,3,4} are
  round-3 (head) slots, {37,39,40,46,54,58} are round-14 (drain) slots.
- Gather path needs the `fvp_p_3` broadcast (was gated behind `D3_GATHER_TAIL>0`);
  the mask branch now also allocates it. With the default mask always active this
  +1 setup const is live (funds the gathers).

## Gate (all pass)
`parity_check.py` 0 violations · `algebra_check_ported.py` ALL-PASS ·
`tests/submission_tests.py` **1120** · `PSPACE=0` **1180** (≤1187 gate).

## Remaining headroom
d3 sparse gather is a strong tail/packing lever (−13, not the −2 the sweep implied).
Progression 1134→1132 (combo local opt)→1121 (full-space SA)→1120 (SA refine):
diminishing returns confirm the d3-sparse axis is **converged around 1120**. Further
d3 gains are <1 cycle. The remaining roofline headroom (ceiling 814) is on the
**load-floor axis** — a scratch-free d4 gather cut (#26 gated) — not more d3 masking.
Probes: `anneal_d3_mask.py` (full-space), `anneal_d3_mask3.py` (dual-gate refine).

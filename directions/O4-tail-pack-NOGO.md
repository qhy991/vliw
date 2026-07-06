# O4 tail-packing (pos_offset) — NO-GO @ 1111 (2026-07-06)

Branch: `explore/v111-tail-pack` (from `explore/wave6-1120` @ 1111).
Goal: compress `tail = realized − max(floor) = 1111 − 1083.5 = 27.5` via pure
scheduling (op-count invariant). Fixed masks: `D3_GATHER_MASK={0,1,2,3,4,34,35,44,45,50,54}`,
`D4_COLD_MASK={7,12,16,22,24,33,37}`.

## Live lever inventory (measured)
Of the four candidate tail levers in the axis brief, only **pos_offset** is live:
- **pos_offset** (`_POS_OFFSET_PSPACE_32x16`): the sole live, op-count-invariant lever.
- **rotation count/set**: default already tries all 32; argmin is rot 27 for the
  shipped offset. Not a free parameter — it is the objective, not a knob.
- **mtmp groups** (`_num_mtmp_groups`): op-count invariant but **3 is optimal**
  (G=2 → 1139, G≥4 → scratch overflow). Confirms V10.
- **`_step`**: dead when `pos_offset` is set (offset overrides the diagonal).
- **emit-order / windup-drain overlap**: setup `prefix` and body are already
  scheduled **jointly** (`Scheduler().schedule(prefix + rnd)`, line ~1496) — no
  separate overlap lever exists. Confirms S8.
- **vstore placement**: already emitted per-vector right after each vector's last
  round; drain stores land on the idle `store` engine (floor 16), not binding.

## The oracle-bias trap (new, important)
The shipped offset was tuned by `anneal_pspace.py` with a **single fixed oracle
rotation (rot=27)**. But the argmin rotation SHIFTS as the offset changes:
measured on 8 random offset neighbors, the true best rotation landed at
{25,26,28,29}, and **rot27 misread those offsets by up to +228 cycles** (read
1339 when the true best was 1120). A single-rot oracle therefore reports every
perturbed offset as a large regression (acc≈0.02) and never searched the joint
(offset × rotation) space. **Fix:** oracle = min over a rotation window {25..29}
(driver `experiments/anneal_pos_offset.py`, env `WIN`). Any future emit-order/
offset SA on this graph MUST sweep a rotation window, never a single rot.

## Result: NO-GO — 1111 is the pos_offset floor
With the corrected multi-rotation oracle, **four independent SA runs** all
converge to 1111:
- warm seed=2026 T0=2.0, seed=7777 T0=3.5, seed=4242 T0=5.0 (2000 iters each):
  all best FULL = **1111**, acceptance 0.04–0.17 (genuinely exploring, not
  oracle-stuck).
- cold random restart seed=13131 T0=6.0, window {23..30}, 2000 iters: best FULL
  **1120** (never reached 1111 — the shipped offset sits in a superior basin
  random restart cannot find).

## Why the tail is structural, not packable
Abstract perfect-packing floor = max(ceil(2143/2)=1072 load, ceil(12440/12)=1037
alu, ceil(6162/6)=1027 valu) = **1072**. Realized 1111 leaves 39 cycles, of which
the measured tail is windup(~33 load-idle slots) + drain(~20) + setup(2) = 27.5
cycles of load-engine idle. This is the **S9 structural lesson**: the drain
(cyc ~1088–1110, load=0) is the last-started vectors running their final depth-0/1
rounds, which have **no gathers** — there is no load work in the DAG to place in
that window. pos_offset can shift *when* vectors run but cannot manufacture load
work in the drain. It is already at the schedule-local optimum.

## Resurrection condition
Only after a **load-floor mover lands** (load used drops materially below 2143,
so the drain has gather work to fill, OR the binding engine changes). Then
re-run `anneal_pos_offset.py` (multi-rot oracle) on the new graph. Until then
the tail is at its floor and O4 contributes nothing standalone — its value is
purely additive once O1/O2/O3 lower a real engine floor.

## Verification (baseline unchanged)
```
parity_check: 0/4096 violations
algebra_check_ported: ALL-PASS
tests/submission_tests: CYCLES 1111 (PSPACE=1)
PSPACE=0: CYCLES 1180 (≤1187 gate)
```

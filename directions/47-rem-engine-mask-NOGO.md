# Direction #47: traverse `rem` engine mask (`%`→`&` valu→alu) — NO-GO (neutral tail, regressing prefix)

**Baseline:** `explore/w7-optimize` @ **1085** cycles (PSPACE=1; PSPACE=0 1181).
**Date:** 2026-07-08.

## Hypothesis (why it looked new and promising)

The 1085 graph is **valu-bound** with large alu slack:

```
load  1043.5      valu  1056.3  (BIND)     alu  914.7      F = (8·valu+alu)/60 = 1028.0
realized 1085     tail gap ~28.7
```

`valu` floor (1056.3) sits **28 cycles above the co-bind wall F (1028)**, and alu
idles at 914.7 (≈141 slot-cycles slack). Every prior valu→alu lever moved the
**hash XOR combines** (`_combine_mask`, already SA-annealed) or the `val^node`
XOR (`_xor_mask`). But the profile exposes **three op classes the annealer never
had access to**:

```
valu ops: multiply_add 2432 (locked), ^ 1743 (annealed), >> 1024 (locked),
          % 448  ← NEW movable,  - 192 / + 250 (traverse, NEW movable),
          vbroadcast 231 (d4-cold, locked), & 10, < 8
```

`rem = val % 2` is **bit-identical to `val & 1`** for uint32, and `&` emits on
either valu (1 slot, `v_alu`) or alu (8 per-lane slots, `v_alu_scalar`). So the
448 `%` instances are a free 0/1 engine choice, exactly like combines — and F is
**invariant** to the move (removing 1 valu op and adding 8 alu ops keeps
`8·valu+alu` constant). Moving ~170 valu-equivalent ops would pull valu floor
1056.3 → F 1028, a **−28 floor** prize if realized tracked the floor.

## Implementation (shipped, default-off)

New `_rem(dest, val, c)` helper + `_rem_mask` / `_rem_no` (per-rotation reset),
mirroring `_combine`. Env knobs:

- `REM_ALU_N=k` — move the **first** k rem instances (emit order) to alu `& 1`.
- `REM_ALU_TAIL=k` — move the **last** k (drain-targeted) to alu.
- `REM_MASK=<json 0/1>` — explicit per-instance mask.

Default (all env unset / `REM_MASK` unset) → all rem on valu as `%` →
**byte-identical to the shipped 1085 build** (verified: parity 0/4096,
`submission_tests` 1085, PSPACE=0 1181).

## Measurement — NO-GO

**Prefix (first-N → alu):** monotonic regression, no win at any N.

| REM_ALU_N | 32 | 64 | 96 | 128 | 160 | 200 | 256 | 320 | 448 |
|---|---|---|---|---|---|---|---|---|---|
| realized | 1111 | 1127 | 1139 | 1145 | 1152 | 1172 | 1184 | 1193 | 1251 |

**Drain-targeted (last-N → alu), after `_rem_cap=448` fix (was broken: used 480):**

| REM_ALU_TAIL | 0 | 8 | 16 | 32 | 48 |
|---|---|---|---|---|
| realized | **1085** | 1087 | 1090 | 1094 | 1099 |

(Earlier `TAIL≤32 → 1085` was a bug — `_rem_total=480` never matched emit order, so
no instance was actually moved.)

**Joint omni-anneal (`combine,offset,rem`, 200 iter, rot29 oracle):** seed and
best both **1085** — no improvement; champ not overwritten.

Correctness with the lever active stays bit-exact (`REM_ALU_N=64`: parity 0,
submission OK 1127).

## Verdict & root cause

**NO-GO — same structural wall as V11 (flip-p) and the xor→alu probe.** The valu
floor drop is real but **absorbed**: realized 1085 is limited by the **drain
critical path** (LESSONS S11: hash 6-stage serial chain + drain-serial-rounds ≈
28c tail), not by the valu floor. Worse, `rem` is a **direct RAW producer** of
the traverse `p ← 2·p + rem` (or `p = i2p1 − rem_x`), so putting it on the
8-slot alu engine **lengthens the traverse critical path** — the prefix
regression is steeper than a pure floor-absorption would predict (structurally
identical to the #29 `vaddr→flow` NO-GO: producer-of-a-hot-consumer).

## Silver lining (resurrection condition)

The 448 `rem` instances are wired into `omni_anneal.py` as class `rem` for future
joint search after a load-floor mover. A 200-iter `combine,offset,rem` run @1085
found **no win** (local optimum). Keep `REM_*` default-off; do not retry rem-alone
on this graph.

## Reproduce

```bash
for N in 32 64 128 256 448; do REM_ALU_N=$N python -c \
  "from perf_takehome import KernelBuilder; kb=KernelBuilder(); kb.build_kernel(10,2047,256,16); print(N, len(kb.instrs))"; done
REM_ALU_TAIL=32 python tests/submission_tests.py   # OK, CYCLES: 1085 (neutral)
python tests/submission_tests.py                    # OK, CYCLES: 1085 (default off)
```

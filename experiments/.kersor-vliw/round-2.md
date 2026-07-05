# Round 2 — #28 const→flow rebalance — LANDED (1156 → 1152, −4)

**Date:** 2026-07-05
**Lever:** const-load engine rebalance (new; not in kill registry)
**Result:** CYCLES 1156 → **1152** (128.24×); PSPACE=0 1190 → 1189.

## Root cause

After #15, `load` binds (2140/2 = 1070). The 58 setup `const` ops execute on the
**load** engine and land in the load-saturated windup (cycles 0–47, L2) while the
`flow` engine is idle there (F0) and `add_imm(dest, a, imm)` is a **flow** op
(floor 704, ~450 slots slack).

## What worked

Route the first **12** distinct non-zero setup consts to
`add_imm(dest, zero_seed, val)` on flow instead of `const` on load. One shared
zero-seed (a single real const load) sources them.

Sweep (real `build_kernel`, PSPACE=1):

```
N_flow:  0    6    8   10   12   14   16
cycles: 1156 1155 1154 1153 1152 1154 1157
```

- **N=12 optimal.** Beyond ~12 the zero-seed RAW chain + 1-slot flow engine
  serialize and regress (N=16 → 1157).
- Multiple zero-seeds (S=2,3) give **no** improvement — the win is windup load
  relief, not seed contention.

Engine profile @ 1152: load 2129/2 = **1064.5** (was 1070.5), flow 716 (was 704),
valu 1002.8, alu 1036.7. Load still binds; tail gap shrank ~4.

## Implementation

`scratch_const` gains a `_const_flow_n` knob (default 12, env `CONST_FLOW_N`).
`add_imm` is arithmetically exact, so correctness is untouched (parity + algebra
pass). N=0 restores all-load behavior.

## Why the scratch levers (round 1) were NO-GO

- **node/addr pooling** (the only unkilled clean-reclaim): G=16 → 1319 (+163) to
  free 256w; genuinely live across the 32-vector pipeline. Dead.
- **mtmp groups**: G=2 frees 73w for +14 cycles, G=1 frees 97w for +19; neither
  reaches the 128w d4 gate cleanly and both regress. Confirms LESSONS L2/L3.
- **dead consts**: only 13 words genuinely dead (vctr/vstride/grp_base/cond/mtmp
  alias), all reused. No 79-word clean reclaim exists → **#25 gate blocked**, so
  #26 d4-table stays gated. The const→flow lever is orthogonal (attacks the load
  floor directly, no scratch needed).

## Next

- Re-anneal (Rule C) may repack the −4 into more; the 11 remaining setup consts
  still sit on load but in less-saturated cycles.
- Drain const-loads: none (all consts are windup, span 0–47).
- Load floor still 1064.5 → the d4-gather-cut (#26) remains the big prize but is
  scratch-gated.

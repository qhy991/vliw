# W7 @1094 exploration ledger (2026-07-06)

**Baseline:** `explore/wave6-1111` @ **1094** (`cac5471`). Worktree: `vliw-w7-optimize`.

## Engine profile (PSPACE=1, rot29)

```
load  1035.5  BIND
valu  1031.5
F     1025.1
alu    999.3
flow   859.0
tail    58.5  (58 cycles with 0 load slots; 117 free load-slots total)
```

Gather breakdown (rot29): d3=3, d4=53, d5–d10=32 each → **1984** scalar gather loads.

## Probes run

| Probe | Result |
|-------|--------|
| `anneal_pos_offset.py` (rot29, 5k iters) | **NO-GO** — stuck 1094 |
| `anneal_d3d4_joint.py` (3×4k, gate 1094) | **NO-GO** — oracle never <1094 (restart 1 touched 1096 only) |
| `omni_anneal.py` (offset+combine+xor, 8k) | **NO-GO** — best FULL32=1094 |
| `probe_w7_d4_expand.py` (+1 d4 cold each) | **NO-GO** — 0/53 wins |
| d4 cold −1 each | **NO-GO** — all ≥1094 |
| `step` sweep 1..16 | **NO-GO** — all 1094 |
| `COMBINE_HEAD/TAIL` sweep | **NO-GO** — best 1094; `B0_CARRY=0` → 1136 |
| `CONST_FLOW_MASK` 1-bit flips | **NO-GO** — 0/58 beat 1094 |
| `anneal_const_flow_mask.py` (rot29, 1.5k) | **NO-GO** — best **1103** |
| d3/d4 1-bit greedy (full-32) | **NO-GO** — 0 wins |
| `D4_MUX` / `NODE_POOL_G` | **ERR** scratch |
| d5 cold-table mux prototype (`D5_COLD_MASK`) | **NO-GO** — 1 instance → **1127** (+33c); flow cost dominates |

## Interpretation

- 1094 is a **joint optimum** over B0_CARRY + sparse d3/d4 masks + rot29 offset; single-axis SA/shuffle is absorbed.
- **58.5c tail** is structural load-idle in windup/drain; 117 spare load slots cannot be filled without adding binding work elsewhere.
- `GATHER_FREE=1` schedules at **993** (wrong output) — sub-1000 is scheduler-feasible only if **d4/d5+ gather op count** drops with a correctness-preserving representation cheaper than E2 d4 cold + flow tournament.
- d5 E2-style cold mux (4 inline vloads + 16-way×2 + b4) is **far too flow-heavy** per instance; partial masks still regress.

## Next (if continuing)

1. **Correctness-preserving d5+** must beat `8 loads` vs `~20 flow + 4 vload` *after packing* — likely needs **mem-side** or **cross-round prefetch**, not another on-scratch tournament.
2. Re-open offset/mask SA only **after** a real load-floor mover lands (O4 resurrection per `LESSONS.md` S10).
3. Use `scripts/setup-wave7-kersor-worktrees.sh` for parallel KerSor lanes on exotic structural ideas.

## Reproduce

```bash
cd vliw-w7-optimize
python tests/submission_tests.py              # CYCLES: 1094
python experiments/probe_w7_d4_expand.py
ORACLE_CENTER=29 ITERS=3000 python experiments/anneal_pos_offset.py
python experiments/anneal_d3d4_joint.py --gate1 1094 --gate0 1184
```

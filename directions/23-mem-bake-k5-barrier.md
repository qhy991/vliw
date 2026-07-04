# Direction #23: Universal K5-deferral via lazy mem-bake under idle load slots (moonshot §d)

**Baseline:** `explore/merged-floor` @ **1156**. K5-deferral (#02) is **selective — only
7 of 16 rounds** defer the trailing `^K5`, because gather rounds (d≥4) read raw node
values from mem and can't carry a pre-baked `node^K5`. The 9 non-deferring rounds each pay
1 extra valu op per vec = **288 valu ops**. Deleting them drops the valu floor ~48.

**Thesis (moonshot §d, MEDIUM-risk).** Bake `node ← node ^ K5` into the gather subtree of
`mem` (`tree[15..2046]`, ~2032 words), then *every* round can defer K5 and gather the
baked value directly. The bake is `~254 vload + ~254 valu + ~254 vstore ≈ 380 cycles` —
net-negative if done as a serial setup phase. **The win is hiding it under idle load
slots.** The windup (~first 256 cycles) runs load at ~1.8/2 slots; the idle 0.2/cycle over
~256 cycles ≈ 50 free load slots, plus the store engine is idle *everywhere* (store floor
16 vs 1070). If the bake piggybacks on idle load/store, its cost → near-zero.

- **Priority: 3 (independent; pairs with #20+#22 for margin below 1000).**
- **Confidence: LOW-MEDIUM (~25%).** The blocker is a **scheduler phase barrier**: rounds
  reading baked nodes must be ordered after the bake completes for the addresses they touch.
- **Effort: 3–5 days** incl. the scheduler extension.

## 1. Kill test (DO FIRST — measure idle load slots)

```bash
# On the current 1156 schedule, count load-engine idle slots in cycles [0, 300).
python watch_trace.py   # or instrument the scheduler to emit per-cycle slot occupancy
```
- If load idle slots in the windup **≥ 254** (enough to hide all the bake vloads/vstores),
  proceed. The bake is `254 vload + 254 vstore` on load/store engines.
- If **< 150**, the bake can't hide → net-negative → **KILL** and document.

## 2. The phase barrier (the real work)

The current scheduler models only RAW/WAR/WAW on scratch addresses; it does **not** model
mem dependencies between a `vstore` (bake) and a later `load` (gather) at the same mem
address. Options:
1. **Coarse barrier:** emit a single `after` edge from all bake stores to the first
   gather round. Simple, correct, but serializes bake fully before round 4 — kills the
   hiding. Only viable if the bake genuinely fits in the pre-round-4 windup.
2. **Fine mem-dep tracking:** extend `Op.reads/writes` to a separate mem-address space so
   the existing dep machinery orders bake-store → gather-load per address. More work,
   preserves overlap. Preferred if §1 shows tight windup budget.

## 3. Payoff

If the bake hides for free: delete 288 valu (9 rounds × 32) → valu floor 1013.5 → ~965.
Stacked on #20 (load ~815) and #22, realized target **< 1000**. Standalone (no #20),
valu-bound realized ~1108.

## 4. Verify / kill criteria

```bash
python parity_check.py && python algebra_check_ported.py   # baked mem must yield identical results
python tests/submission_tests.py            # OK, CYCLES < 1156
PSPACE=0 python tests/submission_tests.py
```
- **Kill if:** windup idle-load < 150 (§1), OR the phase barrier serializes the bake into a
  net cycle *increase*, OR baked-mem correctness fails (the K5 XOR must be applied exactly
  once per node and un-baked nodes must never be read raw).

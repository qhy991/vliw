# Direction #24: Close the 86-cycle tail gap — windup/drain restructure + store-broadcast setup pipe

**Baseline:** `explore/merged-floor` @ **1156**. Binding load floor 1070.5, realized 1156
→ **tail gap ≈ 86 cycles** of pure packing loss (windup fill + drain empty + setup burst).
This is the low-risk, always-something lever: it needs no algebra and can't regress
correctness (scheduling only). It also *compounds* with #20/#22/#23 — every floor drop
they land re-exposes tail gap for this direction to reclaim.

- **Priority: 2 (runs in parallel; guaranteed-ish small win, de-risks the portfolio).**
- **Confidence: MEDIUM-HIGH for 10–25 cycles.** The omni-anneal (#17) already chips
  combine/extract/offset; this direction attacks the *structural* tail, not the mask.
- **Effort: 2–3 days.**

## 1. Where the 86 cycles go (measure first with watch_trace.py)

Split the gap into three buckets and size each:
1. **Setup burst** — ~30 vbroadcasts serialize on valu (6 slots → ≥5 cycles even fully
   packed) while load/store sit idle. **Store-broadcast pipe (moonshot §c):** move half
   the broadcasts to `store scalar→mem` + `vload`, running on the idle load/store engines
   in parallel with the valu broadcasts. Splitting 30 → 15 valu + 15 (store,vload) can
   shave the setup floor by a few cycles. Reuse the dead mem region below
   `header + n_nodes` (tree values are consumed after the initial vloads).
2. **Windup fill** — the first ~256 cycles ramp from 1 to full engine occupancy as vectors
   enter the pipeline. Reordering which vectors/depths enter first (the rotation search
   already explores this, but only globally) — try a *windup-specific* vector ordering
   distinct from the steady-state order.
3. **Drain empty** — the last rounds have fewer independent vectors in flight. The
   `skip_idx_update` on the final round already helps; check whether the last 2–3 rounds
   can borrow work (e.g. prefetch next-round gathers early) to keep engines full.

## 2. Levers (all scheduling-only, correctness-safe)

- **Store-broadcast setup pipe** (§1.1): concrete, ~2–4 cycles, no scratch cost.
- **Windup/drain vector reordering:** add a per-phase rotation offset to the omni-anneal
  genome (distinct windup vs steady vs drain orderings) instead of one global rotation.
- **Scheduler priority-key sweep:** the greedy scheduler uses `KEYS[0]` (height-then-
  successor). Sweep all 5 keys × the rotation search; a different key may pack the drain
  tighter (CP-SAT proved ≤1 cycle from optimal *per fixed key*, but not across keys).

## 3. Method

1. `watch_trace.py` → per-cycle per-engine occupancy; quantify setup vs windup vs drain
   contribution to the 86-cycle gap.
2. Land the store-broadcast pipe first (smallest, safest, no scratch).
3. Add per-phase rotation to `omni_anneal.py` genome; re-anneal.
4. Sweep scheduler `key_idx` in the rotation search.

## 4. Verify

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py            # OK, CYCLES < 1156
PSPACE=0 python tests/submission_tests.py
```
- **Kill a lever if:** watch_trace shows that bucket is already ≤ its engine floor (no
  slack to reclaim). Record the measured setup/windup/drain split so future sessions don't
  re-measure.

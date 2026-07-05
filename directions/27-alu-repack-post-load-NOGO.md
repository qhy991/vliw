# Direction #27: alu→valu repack after load-floor drop — **NO-GO @ 1156** (precondition unmet)

**Branch:** `explore/27-alu-repack-post-load` @ 1156 baseline.
**Verdict:** **NO-GO on the 1156 graph** — alu is a **sub-floor** (1036.7 < load
1070.0), so every alu→valu move is absorbed by the load wall (payoff 0). This is
exactly the kill criterion the #27 direction doc names for "run without a load
drop." The thesis itself is **validated** on the load-cut (D4_FREE) schedule and
is banked for the post-#26 world. Baseline 1156 untouched.

**Resurrection condition:** a load floor-mover lands (`#26` d4-gather-cut, gated
on `#25` scratch ≥128). Then re-run the repack anneal on the new graph — it is
worth **~61 cycles** there (see §2).

**Re-priced @ 1152 (#28 const→flow rebalance landed, Rule B):** #28 dropped the
load floor 1070.0 → **1064.5** (load 2140→2129, flow 704→716). alu 1036.7 is
still **28 slots below** the load wall — **verdict UNCHANGED, still NO-GO**. The
gate (load floor < alu 1036.7) needs ~28 more cycles of load drop; #28 does not
cross it. Only a d4-scale load cut (#26) can. The equilibrium math in §1/§2 is
floor-structure-identical (same alu/valu op counts); only the load number moves.

---

## 1. Kill @ 1156 — alu is sub-floor, load binds (Rule A absorption)

Measured on this worktree (`experiments/probe_27_repack.py`, PSPACE=1, rot27):

```
LIVE 1156 graph:
  ops : valu=6017 alu=12440 load=2140 flow=704
  floor: valu=1002.8  alu=1036.7  load=1070.0  flow=704.0  F=1009.6
  realized=1156  binding=load 1070.0  tail=86.0
```

`load 1070.0` is the wall; `alu 1036.7` is **33 slots below it**, `valu 1002.8`
is **67 below**. The whole premise of #27 — "move engine-neutral ops alu→valu
where valu has slack" — only pays if alu is *binding*. It is not.

**Repack equilibrium on the live graph** (move x combines alu→valu until the alu
and valu floors meet):

```
  x* ≈ 41 combines alu→valu  ->  alu 1009.3, valu 1009.7
  binding floor UNCHANGED at load 1070.0   (both new floors still < load)
```

A *perfect* alu↔valu rebalance leaves the binding floor at 1070.0 and the
realized number at 1156. **Every alu→valu move is absorbed** — LESSONS Rule A.
This is the identical mechanism that killed V7 (valu deletion @ load-bound) and
V1/#22 (extract purge): sub-floor engine work is free to shed and free to move,
and buys nothing until load stops binding.

## 2. Thesis validated on the D4_FREE (load-cut) schedule — banked for post-#26

The D4_FREE probe (delete all depth≥4 gathers for free — same probe as #20 Kill
2, reproduced here on the live graph) flips the binding engine to alu, and *then*
the repack has real headroom:

```
D4_FREE probe (depth>=4 gathers deleted, addr-add + 8 loads each):
  ops : valu=5761 alu=12440 load=92 flow=704
  floor: valu=960.2  alu=1036.7  load=46.0  flow=704.0  F=975.5
  realized(probe)=1089  binding=alu 1036.7  tail=52.3      <- matches LESSONS §4 (1088/1036.7)

  repack equilibrium: move x* ≈ 92 combines alu->valu
    -> alu 975.3, valu 975.5, load 46  =>  binding 975.5  (F floor)
```

So on a load-cut graph the alu→valu repack pulls the binding floor
**1036.7 → 975.5 ≈ −61 cycles of floor** (realized win gated by tail packing on
top). The direction is sound; only its precondition (load drop) is missing.
Note the equilibrium lands on the **F co-bind floor 975.5** — repacking past
alu=valu is itself F-neutral, so F becomes the new hard limit and the anneal
should stop there, not chase alu below valu.

## 3. Empirical corroboration — omni_anneal alu↔valu found nothing @ 1156

`python experiments/omni_anneal.py --classes combine,extract,offset --iters 4000`
on the 1156 graph: seed rot27=1156 / FULL32=1156, **no improving move accepted**
(consistent with LESSONS S3 — the seed champ is a strong local optimum and the
binding engine is load, which no engine-mask class touches). The omni-anneal
combine/extract/xor classes are exactly the alu↔valu repack knobs #27 asks for;
they are already wired and already at their optimum for *this* floor structure.

## 4. Why not just cut load here — pointer to the real blocker

The load-floor lever that would flip alu to binding is a d4-scale gather cut
(`#26`), needing a 128-word broadcast table. **Update @ 1152:** LESSONS §3
(V9/V10) now records the `#25` scratch reclaim as **structurally blocked** — no
clean ≥79-word source exists (only 13 words genuinely dead; mtmp reduction
regresses +14/+19c). So the #26 d4-table path is blocked *at the scratch gate*,
not merely unlanded. The realistic resurrection path for #27 is therefore a
**scratch-free load-floor mover** that reaches below alu 1036.7 — #28's
const→flow (−5.5) is the first of that class but far too small; #27 needs the
load floor pushed a further ~28 cycles under, from load-engine work that needs no
resident broadcast table. Until then #27 is **parked, not workable** — it cannot
move the number by itself and must not burn anneal iterations trying.

## 5. Verify (baseline untouched)

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py            # OK, CYCLES: 1156 (unchanged)
PSPACE=0 python tests/submission_tests.py   # OK, CYCLES: 1190 (unchanged)
```

Probe (floor-measurement only; D4_FREE build is intentionally not correct —
deleted loads leave `node` undefined — so it is never run for correctness):

```bash
python experiments/probe_27_repack.py
```

## 6. Handoff

- **When #26 lands:** rebuild `omni_anneal.py --seed-only` on the new graph,
  confirm alu binds, re-point the combine/extract `flip_bias` toward **alu→valu**
  (invert the 0.65 valu→alu default), and run `--classes combine,extract,offset
  --iters 20000+`. Target: close realized − max(F, alu, load) ≤ 40; expected
  binding-floor drop ~alu 1036.7 → F 975.5. Promote champ only after full-32 +
  `check_correct` gate.
- This doc + `experiments/probe_27_repack.py` are the reusable artifact.

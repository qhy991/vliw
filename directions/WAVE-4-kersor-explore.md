# Wave-4 — KerSor explore @ 1152 (workflow-evolution enabled)

**Baseline:** `explore/merged-floor` @ **1152** cycles (128.24×), PSPACE=1.  
**Binding:** load floor **1064.5**; alu **1036.7** (−28 gap); valu slack ~62.  
**Registry:** read `LESSONS.md` first — do not retry closed levers.

KerSor `/kersor:optimize --mode explore --yolo --allow-workflow-evolution
--allow-workflow-authoring` is the orchestrator. CUDA AKW workflows will **STALL**;
on STALL or `needs_adaptation`, **evolve or author** a VLIW-native workflow that
calls local tools (`omni_anneal.py`, probes, kill-tests) — never ncu/GPU.

---

## Ranked hypotheses (try in order until plateau)

### Tier A — scratch-free load floor (highest ROI, no #25 gate)

| ID | Hypothesis | Mechanism | Expected | Risk |
|---|---|---|---|---|
| **A2** | Extend #28 beyond N=12 | Route remaining 11 setup consts via **store+vload**, **valu add**, or **delayed const** in less-saturated cycles; or split zero-seed chain across 2 seeds | −1..−8 if any engine has windup slack without RAW chain | N>12 regressed; 1-slot flow serializes |
| **A3** | Setup const **schedule reorder** | Emit high-fanout consts before low; interleave flow add_imm with load const to hide RAW | packing only, 0–4c | may be absorbed |
| **A4** | **Drain/windup load fill** | Move non-gather load work into cycles 0–47 idle slots (broadcast deferral, batch const) | tail gap −4..−10 | #24 showed intrinsic gap; retry only if floor drops |
| **A5** | **Partial gather deferral** without d4 table | Reduce scalar gather count via **broadcast-only** depths (reuse landed d3 pattern); no 128w nb table | −8..−20 load ops if algebra-safe | scratch; must not hit L1/L3 traps |

**Unlock condition for #27:** load floor must drop **below alu 1036.7** (~28c / ~57 load ops).
Any Tier-A win that crosses this flips binding → mandatory **alu repack anneal** (~61c banked).

### Tier B — partial d4 cut (prize real, scratch tight)

| ID | Hypothesis | Mechanism | Expected | Risk |
|---|---|---|---|---|
| **B1** | Cherry-pick **#25 recycler** (4 commits) | 49→**79 free** @1152, cycle-neutral | enables smaller mux footprint | still **48w short** of 128w table |
| **B2** | **D4_FREE k∈[12,22]** partial cut | `probe_d4_free.py` sweep: crossover k≈12–14, bottom ~1096 @ k≈32; flow-only select budget | **1100–1110** band if mux fits in 79w | #26 NO-GO for full table; partial may fit |
| **B3** | **Joint anneal**: node/addr pool + partial mux | Accept +10..+14c scratch cost IF combined with gather cut net positive | only if net < 1152 | V9: G=29 costs +33c alone |

### Tier C — structural (long shot)

| ID | Hypothesis | Notes |
|---|---|---|
| **C1** | d5 gather trim after partial d4 | Only if B2 lands; d5 dominated by d4 per #21 |
| **C2** | Hash / traverse algebraic rewrite | #19a NO-GO; only if new algebra-safe op deletion found |
| **C3** | CP-SAT window on windup only | S5: ≤3c on full graph; maybe windup-only sub-window |

---

## KerSor workflow evolution targets

When catalog workflows STALL (`kernel_language=python`, no ncu):

1. **Base:** `Generalist` or `KSearch` (python_reference) — adapt eval to `submission_tests.py` cycles, drop ncu steps.
2. **Author if needed:** `vliw-combinatorial-anneal` workflow:
   - Round loop: structural edit → `parity_check` + `algebra_check_ported` → `submission_tests.py`
   - SA: `omni_anneal.py --classes combine,extract,offset`
   - Probes: `probe_d4_free.py`, `probe_27_repack.py`, `probe_node_addr_pool.py`
3. **Never:** modify `tests/` or `problem.py`; never `--resume` stale champs after op-count change.

---

## Success gates

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py            # OK, CYCLES < 1152 to land
PSPACE=0 python tests/submission_tests.py   # must not regress 1189
```

**Stretch:** < 1100 requires Tier-B partial d4 + #27 repack + tail gap after floor drop.

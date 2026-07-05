# Direction #26 — d4 gather cut: **NO-GO** (gated on #25, gate proven unreachable)

**Status:** NO-GO @ 1152/1156 (2026-07-05). Prize is real (probe-confirmed 63c) but
the **#25 scratch gate is unreachable by clean reclaim**, and per-lane/mtmp reclaim
regresses (L3 poison). Filed after independent 4-angle verification of the gate math.

Branch: `explore/26-d4-gather-cut`. Probe committed (ac7b2a6): `D4_FREE` env flag +
`experiments/probe_d4_free.py`. Default build unchanged.

---

## 1. The prize is real (keep the probe)

`D4_FREE=64` deletes all 64 depth-4 scalar gathers → **1156→1093** (load floor
1070→814, binding flips to **alu 1036.7**). Crossover at k≈14; realized bottoms
~1096 at k≈32. See `26-d4-gather-cut-PROBE.md` for the full sweep + select budget.

**If scratch were available, #26 would be worth ~50–60 cycles.** It is not.

## 2. Why it is gated: the d4 table needs 128 words (irreducible)

The 16-leaf tournament selects `tree[15..30]` per-lane via `vselect(cond, A, B)`,
which picks between two **broadcast** vectors. Each of the 16 leaves must be
broadcast to all 8 lanes → **16 × 8 = 128 words** (`nb15..nb30`). This mirrors the
landed d3 table (`nb7..nb14` = 8 broadcasts = 64w; here d3 uses a vload-holder
`d3_tree_vec` + 8 broadcasts = 72w). Per-lane vselect has no cheaper footprint —
128w is irreducible.

## 3. Why the gate is unreachable: clean reclaim ceiling ≈ 14w, need 79w

Measured on the 1156 base (`scratch_ptr=1487/1536`, 49 free; need 128 → **reclaim 79**).
Full read-set liveness scan over the final schedule:

| clean (liveness-only) reclaim path | words | evidence |
|---|---|---|
| fully-dead setup (`cond`,`grp_base`,`grp_base_v`,`mtmp`,`n_nodes`,`vctr`,`vstride`) | **14** | never read anywhere in final schedule |
| dead `v{j}_vaddr` scalars | **0** | all 31 are read (live) |
| idx/addr/node intra-vector alias | **0** | `v0_addr` & `v0_node` are **both written+read in the same bundles** (20,21,22,23…) throughout the hash — lifetimes fully overlap |
| `tree_lo` / `d3_tree_vec` reuse | **0** | still read by the d2/d3 body muxes |
| **clean total** | **14** | **shortfall 65 words** |

**Last resort `mtmp` 3→2:** +24w but **+14 cycle regression** (violates no-regress
gate); 14+24 = 38 < 79 anyway. FAIL.

**Overlay escape (d4 over d3 table):** even if d3's 72w were fully free, 49+72 = **121
< 128**. And d3 rounds {3,14} are **adjacent** to d4 rounds {4,15}; under the 8-wide
diagonal stagger they are simultaneously live → cannot overlay. FAIL.

## 4. Verdict

Four independent angles (128w irreducibility, 14w clean ceiling, addr/node lifetime
overlap, overlay-ceiling 121<128) all confirm: **the #25 gate cannot open on the
current graph.** #26 is NO-GO until a structural change frees ≥65 more clean words
(e.g. a per-vector footprint reduction that doesn't touch alu — none currently known).

Concurs with LESSONS Rule D (updated by parallel #28 worker: "no clean ≥79-word
reclaim exists").

## 5. Resurrection condition

- A per-vector scratch cut (33w/vec × 32) that frees ≥65 words **without alu ops**, OR
- a d4-table representation cheaper than 16 per-lane broadcasts (none known — vselect
  is broadcast-based), OR
- the diagonal-stagger window narrows so d3/d4 tables stop overlapping (would need a
  scheduling change that itself likely regresses windup/drain).

Then re-run the k∈[14,22] flow-top/valu-muladd-bottom plan from the PROBE doc.

## 6. Kept artifacts

- `experiments/probe_d4_free.py` + `D4_FREE` env flag (guarded, off by default).
- `directions/26-d4-gather-cut-PROBE.md` — prize sweep + select-packing budget.
- This NO-GO — gate-unreachability proof.

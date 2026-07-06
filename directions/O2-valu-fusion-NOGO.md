# O2 valu/F algebraic elimination — NO-GO @ 1111 (2026-07-06)

**Axis:** `explore/v111-valu-fusion` (from `explore/wave6-1120` @ 1111).
**Mandate:** truly reduce the *total* valu op count (fewer muladd/xor/shift) to
lower the F and valu floors — the 8× weight on valu is the highest theoretical
lever to break 1000.

**Verdict:** NO-GO on the 1111 graph. Two independent, measured reasons — the
payoff is zero *and* there is nothing left to eliminate.

Probe: `experiments/probe_o2_valu_absorb.py` (reproduces both parts below).

---

## Reason 1 — valu is a sub-floor engine; any cut is absorbed (payoff 0)

Engine floors on the shipped 1111 graph:

| engine | ops | floor | rank |
|--------|----:|------:|------|
| load | 2167 | **1083.5** | **BINDS** |
| alu | 12440 | 1036.7 | 2nd |
| F = (8·valu+alu)/60 | — | 1028.9 | — |
| valu | 6162 | **1027.0** | sub-floor (−56 below load) |
| flow | 743 | 743 | — |

- **Saturation:** across all 1111 cycles, valu is the *sole* binder in **0**
  cycles. In the 28 load-idle tail cycles (the only place a valu cut could
  plausibly help), valu binds **0**, alu binds **7**. There is no cycle whose
  length a valu reduction could shorten.
- **Sensitivity (decisive):** synthetically dropping valu ops (monkeypatched
  `v_muladd`, cycles==len(instrs) is deterministic) does **not** lower realized
  cycles — it *raises* them monotonically:

  | valu ops | valu floor | realized cycles |
  |---------:|-----------:|----------------:|
  | 6162 | 1027 | **1111** |
  | 5509 | 918 | 1118 |
  | 5055 | 842 | 1120 |
  | 3730 | 622 | 1136 |

  Removing work from a non-binding engine only perturbs the schedule around the
  load wall. This reconfirms LESSONS §V7 verbatim.

## Reason 2 — the hash pipeline is already algebraically minimal

Per-stage minimality over the real `HASH_STAGES` (2-input ISA):

| stage | form | status |
|-------|------|--------|
| s0 | `(a+K0)+(a<<12)` | affine → 1 muladd (minimal) |
| s1 | `(a^K1)^(a>>19)` | xorshift, 3 runtime inputs → **irreducible** |
| s2+s3 | `(a+K2)+(a<<5)` ∘ `(…)^(a<<9)` | **already fused** (−512, landed) |
| s4 | `(a+K4)+(a<<3)` | affine → 1 muladd (minimal) |
| s5 | `(a^K5)^(a>>16)` | xorshift → **K5-deferred** (−224, landed) |

Plus d0 const-fold (idx≡0 ⇒ `2·idx+1≡1`) already landed. Every valid identity in
the pipeline is captured. The remaining muladds (4.75/vec-round) and xorshifts are
structurally irreducible on a 2-input engine. R1 (s2+s3-as-2nd-muladd) and V4
(2-round fuse) are separately proven dead.

---

## Orthogonality note
Even a hypothetical valu elimination would satisfy the orthogonality contract
(pure valu-total cut, no alu/load rise) yet still yield **0 realized cycles** —
orthogonality is necessary but not sufficient; the engine must also *bind*.

## Resurrection condition
Re-price O2 only after O1 (load) **and** O3 (alu) both land below ~1027, i.e.
`max(load, alu) < valu`. Until the binding floor drops under the valu floor, this
axis is dead by construction. This is the same gate that blocks #27 (alu-repack)
and V7.

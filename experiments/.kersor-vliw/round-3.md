# Round 3 — Tier-A scratch-free load probes — NO-GO (stays @ 1152)

**Date:** 2026-07-05
**Levers:** (a) omni_anneal re-anneal @ 1152 graph (Rule C); (b) #29 A2
per-vector vaddr→flow.
**Result:** no improvement; global best stays **1152** (PSPACE=1), 1189 (PSPACE=0).

## (a) omni_anneal re-anneal @ 1152 — NO-GO (confirms S3 @ new floor)

Rule C mandates a re-anneal after the #28 structural change (load floor
1070.5→1064.5). Ran `omni_anneal.py --classes combine,extract,offset --iters
8000` seeded from the 1152 graph. Through it=4500 (T=0.26, near-frozen):
`best_rot=1152 best_FULL=1152`, acceptance decayed 0.38→0.11. Identical
flat-1152 signature S3 documented @ 1156 — the champ is a strong local optimum
on the (combine,extract,offset) manifold at this floor too. Log:
`experiments/.kersor-vliw/omni_round3.log`.

## (b) #29 A2 per-vector vaddr→flow — NO-GO (new kill, Tier-A/A2)

**Hypothesis (WAVE-4 A2):** extend #28 to the 31 single-group per-vector load
addresses. They're `IVP + j*V` — an exact affine offset from the
`inp_values_p` register — so `add_imm(vaddr, ivp, j*V)` on flow is
arithmetically identical. Probe `probe_const_placement.py` proved they land in
windup bundles 13–25 which are **load=2/2 (saturated) with flow=0/1 (idle)** —
seemingly ideal free real-estate that #28's budget-12 never reached.

**Measured (VADDR_FLOW=N sweep, PSPACE=1):**

```
N:      0    2    4    6    8   12   16   24   31
cycles:1152 1159 1168 1163 1162 1161 1160 1161 1170
```

**All N>0 regress.** Root cause: unlike #28's setup consts (which no load op
consumes), each `vaddr` is a **direct RAW producer of its own vload**. Moving it
to the 1-slot flow engine inserts an `add_imm` on the vload's critical path and
serializes the windup — flow being idle in the band is irrelevant because the
dependency, not the slot, is the constraint. Structural NO-GO for vaddr.

**Correction to LESSONS A1 headroom note:** the claim "11 setup consts sit in
less-saturated cycles" is FALSE — 46/47 remaining const-loads are in load=2/2
bundles. But the 31 windup ones are these critical-path vaddrs (dead per above)
and the 16 setup ones are zero-seed-chained (#28 N>12 kill). No free const move
remains.

## State after round 3

Load floor still **1064.5** (binding); alu 1036.7 (−28 gap, #27 still locked).
Both cheap scratch-free const-placement levers (A1 extended, A2) are now
exhausted. The remaining Tier-A items are A4 (drain/windup load fill — S9 says
intrinsic, retry only after floor drop) and A5 (partial gather deferral —
scratch-touching). The real prize stays Tier-B partial d4 (B1 recycler → 79 free,
still 48w short of the 128w table; B2 partial mux k∈[12,22]).

## Next

Per WAVE-4 ranking, A2/A3 const levers are closed. Next candidate is **A5 /
Tier-B B2**: a *partial* gather cut that fits in the 79w the recycler frees
(cherry-pick B1 first), targeting the 1100–1110 band — but that needs the
scratch cherry-pick and is not scratch-free. Escalate to the KerSor
workflow-evolution path (author `vliw-combinatorial-anneal`) only if a
scratch-free structural lever is identified; pure anneal is exhausted (S3).

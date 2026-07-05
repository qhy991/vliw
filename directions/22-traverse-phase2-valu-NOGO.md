# Direction #22: traverse/extract phase-2 valu deletion — **NO-GO (KILL @ 1156)**

**Thesis tested (`22-traverse-phase2-valu.md`, resurrecting `03-round-structure.md`
phase-2):** delete the d2/d3 node-select `&`/`<` extracts (parity-carry: key the
vselect tournament on raw `rem` vectors + re-permuted broadcast tables) to lower the
**binding valu floor**, landing ~1150 or below.

**Verdict: KILL @ 1156.** Confirmed in ~30 min, scheduling-first, no correctness work
and no emitter change. **valu is not the binding floor at 1156 — load is.** The
direction's own premise (doc lines 3–5) is that **#20 lands first** (load → ~815),
*then* valu (~1050) becomes the wall. #20 has not landed on `explore/merged-floor@1156`,
so every valu/flow deletion #22 proposes is absorbed by existing slack.

---

## The decisive measurement (engine profile @ 1156, final scheduled build)

```
engine     ops  cap    floor
valu      6017    6   1002.8      <- 67 slots BELOW load; not binding
alu      12440   12   1036.7      <- below load
load      2140    2   1070.0      <- SOLE BINDING FLOOR
flow       704    1    704.0      <- 35% idle (vselect tournament lives here)
store       32    2     16.0
cycles          = 1156            (86 above even the load floor -> tail packing loss)
```

This is the state my memory (`vliw-15-fusion-landed`) records: after #15's s2+s3 fusion
shed −512 valu, **load(1070) is the sole binding floor, valu(1002.8) is sub-floor.**

## Ceiling probes (zero-cost stubs — measure scheduling effect only)

Stubbed `v_alu_ex` to emit nothing (breaks correctness; isolates the *pure scheduling
gain* of removing exactly the ops #22 targets — no scratch cost, no rem-ring needed):

| Removal (stub) | cycles | Δ vs 1156 |
|---|---|---|
| baseline | 1156 | — |
| **all d2/d3 extracts removed** (the full 384-op target) | **1151** | **−5** |
| extracts **+** all `rem=val%2` removed (impossible lower bound) | 1132 | −24 |
| load floor (unreachable by any valu cut) | 1070 | −86 |

- Deleting the **entire** correctness-preserving removable set — with the scratch/rem-ring
  puzzle (doc risk #4, the "PRIMARY risk") **assumed away for free** — buys **5 cycles**.
  The direction's *optimistic* target was ~1150; the physical ceiling here is 1151.
- Even the fantasy bound (delete extracts *and* every rem op, which is required work) lands
  1132 — still **62 cycles above the load floor**. That 1132→1070 residual is windup/drain
  packing loss, which no valu-side deletion can reach (INDEX.md: "≤1 cycle from optimal for
  the fixed op graph, 99% of bundles have an engine saturated").

## Why every listed candidate is dead here

All three doc candidates target sub-floor engines:
1. **`rem=val%2` fold** — valu, sub-floor (67 slots slack). Absorbed.
2. **Depth-specific traverse specialization** (d1 select vs muladd) — valu, sub-floor.
3. **Arithmetic node-mux** (Lagrange/delta instead of extract+vselect) — moves work off
   **flow** (35% idle) and valu (sub-floor) onto valu. Both have headroom; net zero.

The extracts are *already* engine-masked (`_EXTRACT_ALU_PSPACE_32x16`, `v_alu_ex`): #17's
omni-anneal already sheds 301/320 of them onto alu where valu is idle. There is no binding
valu work left to delete — #15 + #17 already harvested it.

## Scratch reality (independent blocker)

`kb.scratch_ptr = 1487 / 1536` → **49 words free**. The parity-carry mechanism (doc §3.1)
needs a 3-vector rem ring = 768 words naive, or +256 even in the tightest overlap layout.
**Does not fit.** Even if valu were binding, the mechanism could not be built without first
freeing ~200+ words (mem-spill #13 is itself a NO-GO — see `vliw-13-mem-spill-killed`).

## Resurrection condition (for #17 omni-anneal / future waves)

**#22 becomes live only after load drops below ~1010** (i.e. #20 d4-mux-engine-split, or
another load-floor cut, lands and pushes load under the valu floor). At that point re-run
the ceiling probe: if `all-extracts-removed` shows a real gap vs the new load floor, the
correctness work (parity-carry table re-permutation, verified bit-exact on
`reference_kernel2`) and the scratch layout become worth doing. Until then every valu op
#22 would delete is off the binding path — **do not re-chase (per doc §3 kill rule).**

## Reproduce

```python
import types
from perf_takehome import KernelBuilder
def build(stub):
    kb = KernelBuilder()
    if stub:
        kb.v_alu_ex = types.MethodType(
            lambda self,opn,dest,a,b: setattr(self,'_extract_no',self._extract_no+1), kb)
    kb.build_kernel(10, 2047, 256, 16)
    return len(kb.instrs)
print(build(False), build(True))   # 1156 1151  -> ceiling is -5, load-bound
```

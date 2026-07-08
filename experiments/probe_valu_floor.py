"""Cheap floor probe: does cutting ~256 valu traverse ops move realized cycles?

flip-p's whole payoff is deleting 1 valu op per deferring depth-1/2/3 round
(traverse 2-op -> 1-op) plus deferring r3/r14. This monkeypatches the emitter
to DELETE those valu ops (WRONG OUTPUT -- schedule-length only) so we can see
whether realized cycles drop before implementing the correct branch-swaps.

If realized stays ~1094, valu is absorbed (load binds at 1035.5) -> flip-p NO-GO.
If realized drops materially, the packing win is real -> finish the impl.
"""
import sys
from collections import Counter
sys.path.insert(0, ".")
import perf_takehome as P

S = {"load": 2, "alu": 12, "valu": 6, "flow": 1, "store": 2}
SHAPE = (10, 2047, 256, 16)


def profile(kb):
    eng = Counter()
    for b in kb.instrs:
        for e, slots in b.items():
            if e == "debug":
                continue
            eng[e] += len(slots)
    f = {e: eng[e] / S[e] for e in S}
    f["F"] = (8 * eng["valu"] + eng["alu"]) / 60
    return len(kb.instrs), f, dict(eng)


# baseline
kb = P.KernelBuilder(); kb.build_kernel(*SHAPE)
c0, f0, e0 = profile(kb)
print("baseline    ", c0, {k: round(v, 1) for k, v in f0.items()})

# Probe A: delete the SECOND op of every defer-d>=1 p-space traverse by
# neutering v_alu when it's the traverse "-"/"+" that follows a muladd. Too
# fiddly to target precisely; instead delete N valu ops globally to bound the
# packing sensitivity. We drop every K-th valu "-" and muladd in the traverse
# region is hard to isolate, so use a blunt instrument: remove ~256 valu ops
# by skipping the non-defer d>=1 traverse muladd (r3/r14/r4.. gather rounds).
orig = P.KernelBuilder.v_alu


def patched(self, opn, dest, a, b):
    # skip the p-space defer "-" traverse op (idx = (2p+1) - rem_x): this is
    # exactly the op flip-p deletes. Identify by dest==idx-slot and opn=="-".
    if getattr(self, "_probe_cut", False) and opn == "-":
        self._probe_cuts = getattr(self, "_probe_cuts", 0) + 1
        return  # DELETE (wrong output)
    return orig(self, opn, dest, a, b)


P.KernelBuilder.v_alu = patched
kb = P.KernelBuilder()
kb._probe_cut = True
kb.build_kernel(*SHAPE)
c1, f1, e1 = profile(kb)
print("cut all '-' ", c1, {k: round(v, 1) for k, v in f1.items()},
      "cuts=", getattr(kb, "_probe_cuts", 0))
P.KernelBuilder.v_alu = orig

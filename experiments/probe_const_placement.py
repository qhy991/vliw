"""Where do const-loads actually land, and are those cycles load-saturated?

Decisive question for a #28-follow-on: the LESSONS A1 note claims the ~46
remaining setup consts (still `const` on load) "sit in less-saturated cycles"
so moving them off load pays 0. Measure it directly: for every `const` load
slot in the shipped schedule, record its bundle index and that bundle's load
occupancy. A const that lands in a load=2 bundle is stealing a binding slot;
one in a load<2 bundle is free real-estate and moving it pays nothing.
"""
import perf_takehome as P
from perf_takehome import KernelBuilder

setup_end = {"n": None}
_orig_emit = P.KernelBuilder.emit
def emit_spy(self):
    start = _orig_emit(self)
    if setup_end["n"] is None:
        setup_end["n"] = len(self.instrs)
    return start
P.KernelBuilder.emit = emit_spy

kb = KernelBuilder()
kb.build_kernel(10, 2047, 256, 16)
instrs = kb.instrs
sstart = setup_end["n"]
print(f"total={len(instrs)}  setup_end={sstart}")

# find all const slots
const_bundles = []  # (idx, load_occ)
for i, b in enumerate(instrs):
    lo = len(b.get("load", []))
    for slot in b.get("load", []):
        if slot and slot[0] == "const":
            const_bundles.append((i, lo, slot[1], slot[2]))

print(f"\ntotal const-loads still on load engine: {len(const_bundles)}")
sat = sum(1 for (_, lo, _, _) in const_bundles if lo >= 2)
part = sum(1 for (_, lo, _, _) in const_bundles if lo == 1)
print(f"  in load=2 (saturated, moving frees a real cycle): {sat}")
print(f"  in load=1 (partial, alone in bundle):             {part}")

# window distribution of the const-loads
def win(i):
    if i < sstart: return "setup"
    body_i = i - sstart
    n = len(instrs) - sstart
    if body_i < 128: return "windup"
    if body_i >= n-128: return "drain"
    return "mid"
from collections import Counter
wc = Counter(win(i) for (i,_,_,_) in const_bundles)
print(f"  window dist: {dict(wc)}")

# For the saturated ones: what are the OTHER load slots in that bundle? (are
# they gathers we can't move, or other consts we could co-locate?)
print("\n=== saturated const bundles (idx, the 2 load slots) ===")
shown = 0
for i, lo, dest, val in const_bundles:
    if lo >= 2 and shown < 25:
        others = [s[0] for s in instrs[i].get("load", [])]
        print(f"  bundle {i} ({win(i)}): const->{val}  co-load slots={others}")
        shown += 1

# Overall load occupancy in first 60 bundles (the windup where #28 helped)
print("\n=== load occupancy, first 60 body bundles ===")
for bi in range(min(60, len(instrs)-sstart)):
    i = sstart + bi
    lo = len(instrs[i].get("load", []))
    tag = "".join(s[0][:4] for s in instrs[i].get("load", []))
    if lo < 2:
        print(f"  body[{bi:3d}] load={lo}/2  [{tag}]")

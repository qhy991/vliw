"""Head/tail combine re-sweep for the p-space (#12) graph.

p-space deletes ~248 valu ops (valu floor 1111->1070), leaving ALU the sole
binding floor (1112). Rebalance by moving more combines alu->valu (each: alu -8,
valu +1). Rank on a rotation shortlist (fast), confirm winners with a full build.
"""
import os, time
os.environ["PSPACE"] = "1"
from perf_takehome import KernelBuilder

SHORTLIST = [0, 1, 2, 26, 30, 31]
HEADS = [24, 40, 60, 80]
TAILS = [100, 140, 180, 220]

def build(head, tail, rots=None):
    kb = KernelBuilder()
    kb._combine_head = head
    kb._combine_tail = tail
    kb._combine_mask = None
    kb._pos_offset = None
    if rots is not None:
        kb._rotations = rots
    kb.build_kernel(10, 2047, 256, 16)
    return len(kb.instrs)

t0 = time.time()
results = {}
for head in HEADS:
    for tail in TAILS:
        results[(head, tail)] = build(head, tail, SHORTLIST)
        print(f"head={head:3d} tail={tail:3d} -> {results[(head,tail)]}  "
              f"[{time.time()-t0:.0f}s]", flush=True)

print("\n=== shortlist ranking (best first) ===")
ranked = sorted(results.items(), key=lambda kv: kv[1])
for (h, t), cyc in ranked:
    print(f"head={h:3d} tail={t:3d} : {cyc}")

print("\n=== confirming top 3 with full 32-rotation build ===")
for (h, t), _ in ranked[:3]:
    full = build(h, t, None)
    print(f"head={h:3d} tail={t:3d} : FULL {full}  [{time.time()-t0:.0f}s]", flush=True)

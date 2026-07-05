"""#10 re-sweep: COMBINE_HEAD × COMBINE_TAIL on 1208 offset schedule."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from perf_takehome import KernelBuilder

SHORTLIST = [0, 1, 2, 26, 30, 31]
HEADS = [16, 20, 24, 28, 32]
TAILS = [80, 90, 100, 110, 120, 130]
BASELINE = 1208

results = {}
t0 = time.time()
for head in HEADS:
    for tail in TAILS:
        kb = KernelBuilder()
        kb._combine_head = head
        kb._combine_tail = tail
        kb._rotations = SHORTLIST
        kb.build_kernel(10, 2047, 256, 16)
        cyc = len(kb.instrs)
        results[(head, tail)] = cyc
        mark = " ***" if cyc < BASELINE else (" ==" if cyc == BASELINE else "")
        print(f"head={head:3d} tail={tail:3d} -> {cyc}{mark}  [{time.time()-t0:.0f}s]", flush=True)

print("\n=== sorted (best first) ===")
for (h, t), cyc in sorted(results.items(), key=lambda kv: kv[1]):
    print(f"head={h:3d} tail={t:3d} : {cyc}")
best = min(results.items(), key=lambda kv: kv[1])
print(f"\nBEST head,tail={best[0]} -> {best[1]} (baseline {BASELINE})")

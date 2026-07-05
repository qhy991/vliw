"""#01 D3 gather tail × COMBINE_TAIL grid on 1208 graph (fast shortlist)."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from perf_takehome import KernelBuilder

SHORTLIST = [0, 1, 2, 26, 30, 31]
D3_RANGE = range(0, 9)
TAILS = [80, 90, 100, 110, 120]
HEAD = 24
BASELINE = 1208

results = {}
t0 = time.time()
for d3 in D3_RANGE:
    for tail in TAILS:
        os.environ["D3_GATHER_TAIL"] = str(d3)
        os.environ["COMBINE_HEAD"] = str(HEAD)
        os.environ["COMBINE_TAIL"] = str(tail)
        kb = KernelBuilder()
        kb._rotations = SHORTLIST
        kb.build_kernel(10, 2047, 256, 16)
        cyc = len(kb.instrs)
        results[(d3, tail)] = cyc
        mark = " ***" if cyc < BASELINE else (" ==" if cyc == BASELINE else "")
        print(f"D3={d3} tail={tail:3d} -> {cyc}{mark}  [{time.time()-t0:.0f}s]", flush=True)

print("\n=== sorted (best first) ===")
for (d3, tail), cyc in sorted(results.items(), key=lambda kv: kv[1]):
    print(f"D3={d3} tail={tail:3d} : {cyc}")
best = min(results.items(), key=lambda kv: kv[1])
print(f"\nBEST d3,tail={best[0]} -> {best[1]} (baseline {BASELINE})")

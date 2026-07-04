"""Sweep driver for K5-deferral base. Step 1: map rotation landscape @ 20/120."""
import time
from perf_takehome import KernelBuilder

t = time.time()
kb = KernelBuilder()
kb.build_kernel(10, 2047, 256, 16)
rc = dict(kb._rot_cycles)
best = min(rc.values())
ranked = sorted(rc.items(), key=lambda kv: kv[1])
print(f"head/tail = {kb._combine_head}/{kb._combine_tail}  build={time.time()-t:.0f}s")
print("overall best cycles:", best, " (== final instrs:", len(kb.instrs), ")")
print("top 8 rotations:", ranked[:8])
print("all:", ranked)

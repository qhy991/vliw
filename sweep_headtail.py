"""Head/tail grid sweep for the K5-deferral base.

_combine head/tail is a pure scheduling knob (v_alu vs v_alu_scalar compute
identical bits), so we rank candidates on build cycle-count over a shortlist of
known-good rotations, then the winner is confirmed with a full 32-rotation
build + submission_tests separately. Total cycles = 14 setup bundles + body.
"""
import time
from perf_takehome import KernelBuilder

SHORTLIST = [0, 1, 2, 26, 30, 31]   # top cluster from the 20/120 rotation map
HEADS = [8, 16, 20, 24, 32]
TAILS = [100, 120, 140, 160]

results = {}
t0 = time.time()
for head in HEADS:
    for tail in TAILS:
        kb = KernelBuilder()
        kb._combine_head = head
        kb._combine_tail = tail
        kb._rots = SHORTLIST
        kb.build_kernel(10, 2047, 256, 16)
        total = len(kb.instrs)          # setup + best body over shortlist
        results[(head, tail)] = total
        print(f"head={head:3d} tail={tail:3d} -> {total}  "
              f"[{time.time()-t0:.0f}s]", flush=True)

print("\n=== sorted (best first) ===")
for (h, t), cyc in sorted(results.items(), key=lambda kv: kv[1]):
    print(f"head={h:3d} tail={t:3d} : {cyc}")
best = min(results.items(), key=lambda kv: kv[1])
print(f"\nBEST (shortlist) head/tail={best[0]} -> {best[1]} cycles")
print("baseline 20/120 shortlist ->", results.get((20, 120)))

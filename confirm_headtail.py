"""Confirm a head/tail choice with a FULL 32-rotation build (ground truth).
Usage: python confirm_headtail.py HEAD TAIL
Prints total cycles and the winning rotation. Does NOT run submission_tests
(do that separately once the number looks right).
"""
import sys, time
from perf_takehome import KernelBuilder

head, tail = int(sys.argv[1]), int(sys.argv[2])
t0 = time.time()
kb = KernelBuilder()
kb._combine_head = head
kb._combine_tail = tail
kb.build_kernel(10, 2047, 256, 16)
rc = kb._rot_cycles
best_rot = min(rc, key=rc.get)
print(f"head/tail={head}/{tail}  FULL build={time.time()-t0:.0f}s")
print(f"total cycles = {len(kb.instrs)}  best_rot={best_rot} (body={rc[best_rot]})")

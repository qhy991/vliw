#!/usr/bin/env python3
"""Probe helper for vliw-sparse-mask-search workflow.
Usage: probe_d3_mask_cli.py '<json 0/1 list>'
Prints one line: realized=N load=.. alu=.. valu=.. flow=..
"""
import os, sys, json
from collections import Counter
sys.path.insert(0, "/mnt/user_dir/shihaichao/qinhaiyan/vliw-w6-d3-sparse")
os.environ.setdefault("PSPACE", "1")
os.environ["D3_GATHER_MASK"] = sys.argv[1]
os.environ.pop("D3_GATHER_TAIL", None)
import perf_takehome as P
SLOTS = {"valu": 6, "alu": 12, "load": 2, "flow": 1, "store": 1}
kb = P.KernelBuilder()
kb.build_kernel(10, 2 ** 11 - 1, 256, 16)
eng = Counter()
for b in kb.instrs:
    if isinstance(b, dict):
        for e, s in b.items():
            eng[e] += len(s)
fl = {e: eng[e] / SLOTS[e] for e in SLOTS}
print(f"realized={len(kb.instrs)} load={fl['load']:.1f} alu={fl['alu']:.1f} "
      f"valu={fl['valu']:.1f} flow={fl['flow']:.1f}")

#!/usr/bin/env python3
"""Quantify d4 cold vbroadcast tax and D4_HOT_NB feasibility (@1085).

The shipped d4 cold path (12/64 instances) emits 16 runtime vbroadcast per
cold mux via vsel_pair. Setup-broadcast nb15..nb30 eliminates them but costs
+88w scratch vs the resident cold table -- cannot fit without node pooling,
which regresses realized cycles despite lower valu op count.
"""
from __future__ import annotations

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import perf_takehome as P

SHAPE = (10, 2047, 256, 16)
SLOTS = {"load": 2, "valu": 6, "alu": 12, "flow": 1}
COLD_INST = 12  # shipped d4 cold mask cardinality


def measure(**env) -> dict:
    for k, v in env.items():
        os.environ[k] = str(v)
    # reload to pick up env in fresh builder
    kb = P.KernelBuilder()
    kb._rotations = [29]
    kb.build_kernel(*SHAPE)
    eng = Counter()
    for b in kb.instrs:
        for e, slots in b.items():
            eng[e] += len(slots)
    return {
        "cycles": len(kb.instrs),
        "valu": eng["valu"],
        "load": eng["load"],
        "scratch": kb.scratch_ptr,
        "free": P.SCRATCH_SIZE - kb.scratch_ptr,
    }


def main() -> None:
    print("=== W7 d4 cold vbroadcast elimination probe ===\n")
    base = measure(PSPACE=1)
    print(f"Baseline (shipped): cycles={base['cycles']} valu={base['valu']} "
          f"scratch={base['scratch']} free={base['free']}")
    print(f"  depth-4 vbroadcast tax ≈ {COLD_INST * 16} valu ops "
          f"(~{(COLD_INST * 16) / 6:.1f} floor cycles)\n")

    print("D4_HOT_NB=1 (setup nb15..nb30, mux hot path):")
    for npg in (0, 20, 24):
        os.environ.clear()
        try:
            r = measure(PSPACE=1, D4_HOT_NB=1, NODE_POOL_G=npg)
            dv = base["valu"] - r["valu"]
            dc = base["cycles"] - r["cycles"]
            print(f"  NODE_POOL_G={npg:2d}: cycles={r['cycles']} ({dc:+d}) "
                  f"valu={r['valu']} ({dv:+d}) scratch={r['scratch']} free={r['free']}")
        except AssertionError as e:
            print(f"  NODE_POOL_G={npg:2d}: FAIL {e}")

    print("\n=== VERDICT ===")
    print("Runtime vbroadcast elimination saves ~176 valu ops but needs +88w scratch.")
    print("Without node pooling: OOM. With NODE_POOL_G=20: fits but cycles 1187 (+102).")
    print("Pooling WAR serialization dominates; NOT a breakthrough path as-is.")
    print("Sub-1000 still requires correctness-preserving deep gather kill (~440 valu).")


if __name__ == "__main__":
    main()

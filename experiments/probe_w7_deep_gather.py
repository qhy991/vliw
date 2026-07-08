#!/usr/bin/env python3
"""Wave-7 deep-gather feasibility probe on the 1085 graph.

Goal:
  Quantify whether sparse depth-5 gather replacement could theoretically push
  the 1085 kernel below 1000 cycles, before implementing any heavy prototype.

Method:
  1) Measure real op counts on the current shipped kernel.
  2) Apply a conservative cost model for replacing k depth-5 gathers:
       - each replaced instance removes 8 scalar load ops
       - each replacement adds 31 binary selects (32-way tournament)
  3) Optimally split selects across flow/valu/alu lanes to minimize max floor.

This is a lower-bound style model (scheduling-agnostic), used to decide whether
further engineering effort is likely to pay off.
"""
from __future__ import annotations

from collections import Counter
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import perf_takehome as P

SHAPE = (10, 2047, 256, 16)
SLOTS = {"load": 2, "valu": 6, "alu": 12, "flow": 1}

# Cost per binary select when implemented on each engine family.
# flow: one vselect
# valu: sub + muladd style scalarized predicate path (2 valu ops)
# alu: per-lane scalar expansion (8 lanes * 2-ish ALU ops) -> 16 ALU ops
SEL_COST = {"flow": 1, "valu": 2, "alu": 16}

# Depth-5 instance count at K=32 and rounds=16: exactly one d=5 round * 32 vecs
DEPTH5_INSTANCES = 32
SELECTS_PER_D5_INSTANCE = 31


def measure_base_ops() -> dict[str, int]:
    kb = P.KernelBuilder()
    kb.build_kernel(*SHAPE)
    eng = Counter()
    for b in kb.instrs:
        for e, slots in b.items():
            eng[e] += len(slots)
    return {e: eng[e] for e in SLOTS}


def floors(ops: dict[str, int]) -> dict[str, float]:
    return {e: ops[e] / SLOTS[e] for e in SLOTS}


def min_max_floor_after_replacing(base: dict[str, int], k: int) -> tuple[float, tuple[int, int, int]]:
    """Return minimal max-floor and split (flow, valu, alu) select counts."""
    remove_load = 8 * k
    total_selects = SELECTS_PER_D5_INSTANCE * k
    load_after = base["load"] - remove_load
    best = None
    best_split = (0, 0, 0)
    for s_flow in range(total_selects + 1):
        rem = total_selects - s_flow
        for s_valu in range(rem + 1):
            s_alu = rem - s_valu
            ops = dict(base)
            ops["load"] = load_after
            ops["flow"] += s_flow * SEL_COST["flow"]
            ops["valu"] += s_valu * SEL_COST["valu"]
            ops["alu"] += s_alu * SEL_COST["alu"]
            mf = max(floors(ops).values())
            if best is None or mf < best:
                best = mf
                best_split = (s_flow, s_valu, s_alu)
    return float(best), best_split


def main() -> None:
    base = measure_base_ops()
    base_f = floors(base)
    base_bind = max(base_f.values())
    print("=== W7 deep-gather feasibility probe @1085 ===")
    print("base ops:", base)
    print("base floors:", {k: round(v, 1) for k, v in base_f.items()}, "bind=", round(base_bind, 1))
    print()
    print("Assume replacement of depth-5 gather instances only:")
    print(f"  instances={DEPTH5_INSTANCES}, per-instance remove=8 load, add={SELECTS_PER_D5_INSTANCE} selects")
    print("  select cost model:", SEL_COST)
    print()
    print("k  min_max_floor  split(flow,valu,alu)")
    best_row = None
    for k in range(0, DEPTH5_INSTANCES + 1):
        mmf, split = min_max_floor_after_replacing(base, k)
        print(f"{k:2d}    {mmf:8.1f}      {split}")
        if best_row is None or mmf < best_row[1]:
            best_row = (k, mmf, split)
    assert best_row is not None
    print()
    print("best:", best_row)
    if best_row[1] >= 1000:
        print("verdict: with this cost model, sparse d5 replacement cannot reach sub-1000.")
    else:
        print("verdict: model suggests theoretical sub-1000 is possible; worth prototyping.")


if __name__ == "__main__":
    main()

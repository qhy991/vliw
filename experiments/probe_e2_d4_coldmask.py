#!/usr/bin/env python3
"""E2 follow-up: sparse D4_COLD mask probe.

Prefix-k was a NO-GO, but it might be hiding local schedule holes. This probes
individual d4 emit-order instances with D4_COLD_MASK to find any tail/drain
position where the cold mux tax is absorbed.
"""
import argparse
import itertools
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("PSPACE", "1")

import perf_takehome as P

SLOTS = {"valu": 6, "alu": 12, "load": 2, "flow": 1, "store": 1}
FOREST_HEIGHT, ROUNDS, BATCH = 10, 16, 256
BASELINE = 1151
D4_TOTAL = 64


def floors(kb):
    eng = Counter()
    for b in kb.instrs:
        if isinstance(b, dict):
            for e, slots in b.items():
                eng[e] += len(slots)
    fl = {e: eng[e] / SLOTS[e] for e in ("valu", "alu", "load", "flow", "store")}
    fl["F"] = (8 * eng["valu"] + eng["alu"]) / 60.0
    fl["_ops"] = dict(eng)
    fl["realized"] = len(kb.instrs)
    fl["bind"] = max(fl["load"], fl["alu"], fl["valu"], fl["flow"], fl["F"])
    return fl


def build_mask(indices):
    mask = [0] * D4_TOTAL
    for i in indices:
        mask[i] = 1
    os.environ["D4_COLD_MASK"] = json.dumps(mask)
    os.environ.pop("D4_COLD", None)
    os.environ.pop("D4_MUX", None)
    kb = P.KernelBuilder()
    kb.build_kernel(FOREST_HEIGHT, 2 ** 11 - 1, BATCH, ROUNDS)
    return kb


def build_base():
    os.environ.pop("D4_COLD_MASK", None)
    os.environ.pop("D4_COLD", None)
    os.environ.pop("D4_MUX", None)
    # Disable the shipped sparse mask so probes keep reporting deltas vs 1151.
    os.environ["D4_COLD_MASK"] = "[]"
    kb = P.KernelBuilder()
    kb.build_kernel(FOREST_HEIGHT, 2 ** 11 - 1, BATCH, ROUNDS)
    return kb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--positions", default="0,1,2,3,4,7,8,15,16,23,24,31,32,39,40,47,48,55,56,63")
    ap.add_argument("--all", action="store_true", help="probe all 64 singletons")
    ap.add_argument("--combo-size", type=int, default=1, help="probe combinations of this size")
    ap.add_argument("--candidates", default="", help="candidate positions for combinations")
    args = ap.parse_args()

    positions = list(range(D4_TOTAL)) if args.all else [int(x) for x in args.positions.split(",") if x]
    if args.candidates:
        positions = [int(x) for x in args.candidates.split(",") if x]
    combos = list(itertools.combinations(positions, args.combo_size))
    base = floors(build_base())
    print(f"baseline realized={base['realized']} load={base['load']:.1f} "
          f"valu={base['valu']:.1f} flow={base['flow']:.1f}\n")
    print(f"{'mask':>14}  {'realized':>8}  {'load':>7}  {'valu':>7}  {'flow':>7}  "
          f"{'bind':>7}  {'Δreal':>6}")
    best = []
    for combo in combos:
        fl = floors(build_mask(combo))
        dreal = fl["realized"] - BASELINE
        best.append((fl["realized"], combo, fl))
        mark = "  ←" if fl["realized"] < BASELINE else ""
        label = ",".join(str(x) for x in combo)
        print(f"{label:>14}  {fl['realized']:8d}  {fl['load']:7.1f}  {fl['valu']:7.1f}  "
              f"{fl['flow']:7.1f}  {fl['bind']:7.1f}  {dreal:+6d}{mark}")
    print("\nBest positions:")
    for realized, combo, fl in sorted(best)[:10]:
        label = ",".join(str(x) for x in combo)
        print(f"  mask={label} realized={realized} Δ={realized - BASELINE:+d} "
              f"load={fl['load']:.1f} valu={fl['valu']:.1f} flow={fl['flow']:.1f}")


if __name__ == "__main__":
    main()

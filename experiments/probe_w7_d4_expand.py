#!/usr/bin/env python3
"""Greedy d4_cold_mask expansion @ 1094 (no importlib.reload)."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("PSPACE", "1")

import perf_takehome as P  # noqa: E402

SHAPE = (10, 2047, 256, 16)
D4_CHAMP = {6, 7, 9, 16, 21, 23, 24, 25, 29, 32, 35}


def cycles(d4, rots=None):
    os.environ["D4_COLD_MASK"] = json.dumps([1 if i in d4 else 0 for i in range(64)])
    kb = P.KernelBuilder()
    if rots is not None:
        kb._rotations = list(rots)
    kb.build_kernel(*SHAPE)
    return len(kb.instrs)


def main():
    base29 = cycles(D4_CHAMP, [29])
    base32 = cycles(D4_CHAMP, None)
    print(f"base rot29={base29} full32={base32}")

    wins = []
    for i in range(64):
        if i in D4_CHAMP:
            continue
        d4 = set(D4_CHAMP)
        d4.add(i)
        o29 = cycles(d4, [29])
        f32 = cycles(d4, None)
        if f32 < base32 or o29 < base29:
            wins.append((f32, o29, i))
            print(f"  +d4[{i:2d}] rot29={o29} full32={f32}")

    wins.sort()
    print(f"wins={len(wins)} best={wins[0] if wins else None}")


if __name__ == "__main__":
    main()

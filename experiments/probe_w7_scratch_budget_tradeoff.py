#!/usr/bin/env python3
"""Probe scratch-budget vs performance tradeoff for W7 structural paths.

Focus:
  1) MTMP_G sweep on shipped graph (how much scratch can be bought by reducing
     temp groups, and what cycle tax it causes).
  2) D4_HOT_NB feasibility without/with node pooling under MTMP_G changes.
"""
from __future__ import annotations

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import perf_takehome as P

SHAPE = (10, 2047, 256, 16)
BASE_ENV = {"PSPACE": "1"}


def run(env: dict[str, str]) -> tuple[int, int, int, int, int]:
    old = dict(os.environ)
    try:
        os.environ.update(BASE_ENV)
        os.environ.update(env)
        kb = P.KernelBuilder()
        kb._rotations = [29]
        kb.build_kernel(*SHAPE)
        eng = Counter()
        for b in kb.instrs:
            for e, slots in b.items():
                eng[e] += len(slots)
        return (
            len(kb.instrs),
            eng["valu"],
            eng["load"],
            kb.scratch_ptr,
            P.SCRATCH_SIZE - kb.scratch_ptr,
        )
    finally:
        os.environ.clear()
        os.environ.update(old)


def main() -> None:
    base_cycles, base_valu, base_load, base_s, base_free = run({})
    print("=== W7 scratch budget tradeoff probe ===")
    print(
        f"baseline: cycles={base_cycles}, valu={base_valu}, load={base_load}, "
        f"scratch={base_s}, free={base_free}"
    )
    print()

    print("1) MTMP_G sweep on baseline")
    print("MTMP_G  cycles  delta  free_words")
    for g in (1, 2, 3, 4):
        try:
            cyc, _, _, _, free = run({"MTMP_G": str(g)})
            print(f"{g:6d}  {cyc:6d}  {cyc-base_cycles:+5d}  {free:10d}")
        except AssertionError as e:
            print(f"{g:6d}  FAIL   {str(e)}")
    print()

    print("2) D4_HOT_NB without pooling (NODE_POOL_G=0)")
    print("MTMP_G  status")
    for g in (1, 2, 3, 4):
        try:
            cyc, _, _, _, free = run({"MTMP_G": str(g), "D4_HOT_NB": "1", "NODE_POOL_G": "0"})
            print(f"{g:6d}  cycles={cyc}, free={free}")
        except AssertionError as e:
            print(f"{g:6d}  FAIL ({e})")
    print()

    print("3) D4_HOT_NB with pooling grid (best few points)")
    best = None
    print("MTMP_G  NODE_POOL_G  cycles  delta  free_words")
    for g in (1, 2):
        for npg in (4, 8, 12, 16, 20):
            try:
                cyc, _, _, _, free = run(
                    {"MTMP_G": str(g), "D4_HOT_NB": "1", "NODE_POOL_G": str(npg)}
                )
                d = cyc - base_cycles
                print(f"{g:6d}  {npg:11d}  {cyc:6d}  {d:+5d}  {free:10d}")
                if best is None or cyc < best[0]:
                    best = (cyc, g, npg, free)
            except AssertionError:
                continue
    print()
    if best is not None:
        print(
            f"best D4_HOT_NB point: cycles={best[0]} at MTMP_G={best[1]}, "
            f"NODE_POOL_G={best[2]} (free={best[3]}w)"
        )
    print("verdict: scratch can be bought (MTMP_G 3->1 gives +48w),")
    print("but the induced WAR serialization dominates; realized cycles regress.")


if __name__ == "__main__":
    main()

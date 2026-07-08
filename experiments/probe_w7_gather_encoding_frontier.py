#!/usr/bin/env python3
"""W7 deep-gather encoding frontier (d5..d10) under ISA constraints.

This probe is intentionally model-driven: quickly reject structural families
that cannot beat baseline even under optimistic scheduling.

Assumptions encoded from prior probes:
  - No cross-lane permute/vgather: per-lane delivery still required.
  - Baseline per converted instance removes 8 scalar load gathers.
  - Scratch free baseline ~= 21 words on shipped 1085 graph.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import perf_takehome as P

SHAPE = (10, 2047, 256, 16)
SLOTS = {"load": 2, "valu": 6, "alu": 12, "flow": 1}
FOREST_H = 10
ROUNDS = 16
K_VEC = 32
H1 = FOREST_H + 1
SCRATCH_FREE = 21
BASE_CYCLES = 1085


@dataclass(frozen=True)
class Family:
    name: str
    # Per converted instance deltas (converted from gather to this encoding).
    d_load: int
    d_valu: int
    d_alu: int
    d_flow: int
    scratch_words: int
    notes: str


def instance_count_for_depth(depth: int) -> int:
    rounds_at_depth = sum(1 for r in range(ROUNDS) if (r % H1) == depth)
    return rounds_at_depth * K_VEC


def measure_base_ops() -> dict[str, int]:
    kb = P.KernelBuilder()
    kb.build_kernel(*SHAPE)
    eng = Counter()
    for b in kb.instrs:
        for e, slots in b.items():
            eng[e] += len(slots)
    return {e: eng[e] for e in SLOTS}


def bind(ops: dict[str, int]) -> float:
    f_load = ops["load"] / SLOTS["load"]
    f_valu = ops["valu"] / SLOTS["valu"]
    f_alu = ops["alu"] / SLOTS["alu"]
    f_flow = ops["flow"] / SLOTS["flow"]
    f_f = (8 * ops["valu"] + ops["alu"]) / 60.0
    return max(f_load, f_valu, f_alu, f_flow, f_f)


def families_for_depth(depth: int) -> list[Family]:
    # Table size for depth d in p-space: 2^d candidates.
    table = 1 << depth
    # Balanced binary tournament uses (2^d - 1) selects.
    sels = table - 1

    # Heuristic per-select costs from existing code shape:
    # flow vselect: +1 flow
    # cold-table pair-select: ~0.5 valu/vselect amortized by vbroadcast pairs
    # bit extraction: ~d ALU-ish ops per instance
    cold_valu = table // 2
    cold_alu = max(4, depth - 1)

    return [
        Family(
            name="baseline_gather",
            d_load=0,
            d_valu=0,
            d_alu=0,
            d_flow=0,
            scratch_words=0,
            notes="status quo (8 scalar gathers)",
        ),
        Family(
            name="cold_tournament",
            d_load=-8,
            d_valu=cold_valu,
            d_alu=cold_alu,
            d_flow=sels,
            scratch_words=table + 24,
            notes="resident table + runtime pair-broadcast + tournament",
        ),
        Family(
            name="hot_nb_tournament",
            d_load=-8,
            d_valu=0,
            d_alu=max(4, depth - 1),
            d_flow=sels,
            scratch_words=table * 8,
            notes="setup broadcast all leaves; runtime pure flow tournament",
        ),
        Family(
            name="vload_plus_idx_load",
            d_load=0,
            d_valu=0,
            d_alu=0,
            d_flow=0,
            scratch_words=table,
            notes="preload table but still per-lane indexed load",
        ),
    ]


def main() -> None:
    base = measure_base_ops()
    base_bind = bind(base)
    print("=== W7 gather encoding frontier probe ===")
    print("base ops:", base)
    print(f"base bind={base_bind:.1f}, realized cycles={BASE_CYCLES}, scratch_free={SCRATCH_FREE}")
    print()

    print("depth  family               scratch  best_bind  est_cycles  verdict")
    print("-----  -------------------  -------  ---------  ----------  -------")

    for depth in range(5, 11):
        n_inst = instance_count_for_depth(depth)
        for fam in families_for_depth(depth):
            if fam.name == "baseline_gather":
                best_bind = base_bind
                est = BASE_CYCLES
                verdict = "baseline"
            elif fam.scratch_words > SCRATCH_FREE:
                best_bind = float("nan")
                est = 10**9
                verdict = "NO-GO scratch"
            else:
                # Best-case: convert all instances at this depth.
                ops = dict(base)
                ops["load"] += fam.d_load * n_inst
                ops["valu"] += fam.d_valu * n_inst
                ops["alu"] += fam.d_alu * n_inst
                ops["flow"] += fam.d_flow * n_inst
                best_bind = bind(ops)
                # Lower bound estimate: realized >= bind + current tail(28.7).
                est = int(round(best_bind + 29))
                verdict = "candidate" if est < BASE_CYCLES else "weak/no-win"
                if est >= 1000:
                    verdict = "NO-GO <1000"
            bind_txt = f"{best_bind:9.1f}" if best_bind == best_bind else "    n/a  "
            print(f"{depth:5d}  {fam.name:19s}  {fam.scratch_words:7d}  {bind_txt}  {est:10d}  {verdict}")
        print()

    print("Summary:")
    print("- d5+ tournament families are scratch-blocked or flow-explosive under current ISA.")
    print("- preload+idx-load is structurally equivalent to gather on load floor (no gain).")
    print("- No modeled family reaches a credible sub-1000 estimate with current constraints.")


if __name__ == "__main__":
    main()

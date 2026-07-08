#!/usr/bin/env python3
"""Zero-resident-scratch deep-gather probe (W7 @1085).

Target: depth>=5 gather reduction without adding persistent scratch tables.
We evaluate two conservative families:
  A) lane-dedup inside one 8-lane vector (reuse gathered node when p matches)
  B) tiny 2-entry rolling cache per vector (no resident table, temporal reuse)

Both keep memory footprint constant; only execution mix changes.
"""
from __future__ import annotations

import os
import random
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from problem import Input, Tree, VLEN, myhash
import perf_takehome as P

SHAPE = (10, 2047, 256, 16)
FOREST_H, _, BATCH, ROUNDS = SHAPE
H1 = FOREST_H + 1
SLOTS = {"load": 2, "valu": 6, "alu": 12, "flow": 1}


def base_ops() -> dict[str, int]:
    kb = P.KernelBuilder()
    kb._rotations = [29]
    kb.build_kernel(*SHAPE)
    eng = Counter()
    for b in kb.instrs:
        for e, slots in b.items():
            eng[e] += len(slots)
    return {e: eng[e] for e in SLOTS}


def bind(ops: dict[str, int]) -> float:
    return max(
        ops["load"] / 2.0,
        ops["valu"] / 6.0,
        ops["alu"] / 12.0,
        ops["flow"] / 1.0,
        (8 * ops["valu"] + ops["alu"]) / 60.0,
    )


def collect_depth_p_samples(trials: int = 150, seed: int = 0) -> dict[int, list[list[int]]]:
    rng = random.Random(seed)
    out: dict[int, list[list[int]]] = defaultdict(list)
    for _ in range(trials):
        forest = Tree.generate(FOREST_H)
        inp = Input.generate(forest, BATCH, ROUNDS)
        for vec0 in range(0, BATCH, VLEN):
            idx = inp.indices[vec0 : vec0 + VLEN]
            val = inp.values[vec0 : vec0 + VLEN]
            for r in range(ROUNDS):
                d = r % H1
                if d >= 5:
                    base = (1 << d) - 1
                    out[d].append([x - base for x in idx])
                # scalar reference transition (same as problem.py)
                new_idx = []
                new_val = []
                for i in range(VLEN):
                    node = forest.values[idx[i]]
                    v = myhash((val[i] ^ node) & ((1 << 32) - 1))
                    add = 1 if (v % 2 == 0) else 2
                    ni = 2 * idx[i] + add
                    if d == FOREST_H and ni >= len(forest.values):
                        ni = 0
                    new_idx.append(ni)
                    new_val.append(v)
                idx, val = new_idx, new_val
    return out


def estimate_lane_dedup(samples: list[list[int]]) -> tuple[float, float]:
    """Returns (avg_load_saved_per_vec, avg_required_pair_checks_per_vec)."""
    saved = 0.0
    checks = 0.0
    for pvec in samples:
        uniq = len(set(pvec))
        saved += (VLEN - uniq)
        # pairwise equality checks needed to discover duplicates online.
        checks += (VLEN * (VLEN - 1)) / 2
    n = max(1, len(samples))
    return saved / n, checks / n


def estimate_two_entry_cache(samples: list[list[int]]) -> tuple[float, float]:
    """Sequential 2-entry rolling cache over 8 lane accesses."""
    total_saved = 0.0
    total_comp = 0.0
    for pvec in samples:
        cache: list[int] = []
        saved = 0
        comp = 0
        for p in pvec:
            if not cache:
                cache.append(p)
                continue
            # compare against up to 2 cached tags
            comp += len(cache)
            if p in cache:
                saved += 1
            else:
                if len(cache) < 2:
                    cache.append(p)
                else:
                    cache = [cache[1], p]
        total_saved += saved
        total_comp += comp
    n = max(1, len(samples))
    return total_saved / n, total_comp / n


def main() -> None:
    print("=== W7 zero-resident gather probe ===")
    ops0 = base_ops()
    b0 = bind(ops0)
    print(f"base ops={ops0}, bind={b0:.1f}, est_realized~{b0+29:.1f}")
    print()

    samples = collect_depth_p_samples()
    print("depth  avg_saved(lane-dedup)  avg_checks(pairwise)  avg_saved(2-cache)  avg_comparisons")
    depth_stats = {}
    for d in range(5, 11):
        s = samples[d]
        sd, ck = estimate_lane_dedup(s)
        s2, c2 = estimate_two_entry_cache(s)
        depth_stats[d] = (sd, ck, s2, c2, len(s))
        print(f"{d:5d}  {sd:20.2f}  {ck:19.1f}  {s2:17.2f}  {c2:15.2f}")
    print()

    # Cost model (optimistic):
    # - each saved gather removes 1 load op
    # - each equality compare costs 1 ALU op (very optimistic)
    # - each hit requires 1 flow-select to pick cached data vs load (optimistic)
    print("=== optimistic lower-bound model ===")
    best = None
    for d in range(5, 11):
        sd, ck, s2, c2, nvec = depth_stats[d]
        inst = 32  # one round at each deep depth * 32 vecs in 16 rounds

        # A) full pairwise lane dedup
        ops_a = dict(ops0)
        ops_a["load"] -= int(round(sd * inst))
        ops_a["alu"] += int(round(ck * inst))
        ops_a["flow"] += int(round(sd * inst))
        ba = bind(ops_a)

        # B) 2-entry cache
        ops_b = dict(ops0)
        ops_b["load"] -= int(round(s2 * inst))
        ops_b["alu"] += int(round(c2 * inst))
        ops_b["flow"] += int(round(s2 * inst))
        bb = bind(ops_b)

        print(
            f"depth {d}: lane-dedup bind={ba:.1f} (dL={ops_a['load']-ops0['load']}), "
            f"2-cache bind={bb:.1f} (dL={ops_b['load']-ops0['load']})"
        )
        cand = min(ba, bb)
        if best is None or cand < best[0]:
            best = (cand, d)

    print()
    if best:
        est = best[0] + 29
        print(f"best optimistic bind={best[0]:.1f} at depth={best[1]}, est_realized~{est:.1f}")
    print("verdict: zero-resident local reuse cannot offset compare/select overhead;")
    print("it is not a plausible sub-1000 path under current ISA.")


if __name__ == "__main__":
    main()

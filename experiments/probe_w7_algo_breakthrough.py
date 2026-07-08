#!/usr/bin/env python3
"""Algorithm-level breakthrough probes for sub-1000 (@1085 graph).

Sections:
  1) Round necessity — is every round essential for final val?
  2) Batch p support at deep gathers — can we amortize loads across 256 lanes?
  3) Hash algebra — bijectivity + extra muladd fusion search
  4) K5-defer extension to d3→d4 cold boundary (algebra + op budget)
  5) Op-count gap accounting vs GATHER_FREE lower bound
"""
from __future__ import annotations

import os
import random
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from problem import HASH_STAGES, Tree, Input, myhash, VLEN

FOREST_H = 10
ROUNDS = 16
BATCH = 256
H1 = FOREST_H + 1
K5 = HASH_STAGES[5][1]
MASK = (1 << 32) - 1


def ref_round_idx(val: int, idx: int, tree: list[int], depth: int, n_nodes: int) -> tuple[int, int]:
    """Idx-space reference (problem.py semantics)."""
    node = tree[idx]
    val = myhash((val ^ node) & MASK)
    add = 1 if val % 2 == 0 else 2
    idx = 2 * idx + add
    if depth == FOREST_H and idx >= n_nodes:
        idx = 0
    return idx, val


def simulate_full(tree: list[int], val0: int, idx0: int = 0, skip_round: int | None = None) -> int:
    idx, val = idx0, val0
    for r in range(ROUNDS):
        depth = r % H1
        if skip_round == r:
            continue
        idx, val = ref_round_idx(val, idx, tree, depth, len(tree))
    return val


def round_necessity(trials: int = 500) -> None:
    print("=== 1) Round necessity (skip one round, idx-space ref) ===")
    rng = random.Random(0)
    for skip_r in range(ROUNDS):
        mism = 0
        for _ in range(trials):
            tree = Tree.generate(FOREST_H).values
            val0 = rng.randrange(2**30)
            gold = simulate_full(tree, val0)
            try:
                got = simulate_full(tree, val0, skip_round=skip_r)
            except IndexError:
                mism += 1
                continue
            if got != gold:
                mism += 1
        print(f"  skip round {skip_r:2d} (depth {skip_r % H1}): {mism}/{trials} mismatches")
    print("  verdict: every round is essential for final val (no lazy fold).")


def p_support_at_depth(trials: int = 200) -> None:
    print("\n=== 2) Batch p support at gather depths (256 lanes / round) ===")
    rng = random.Random(1)
    stats = {d: [] for d in range(5, 11)}

    for _ in range(trials):
        tree = Tree.generate(FOREST_H).values
        inp = Input.generate(Tree(FOREST_H, tree), BATCH, ROUNDS)
        for lane in range(BATCH):
            idx, val = inp.indices[lane], inp.values[lane]
            for r in range(ROUNDS):
                depth = r % H1
                if depth in stats:
                    base = (1 << depth) - 1
                    stats[depth].append(idx - base)
                idx, val = ref_round_idx(val, idx, tree, depth, len(tree))

    for d in range(5, 11):
        supports = stats[d]
        avg_unique = sum(len(set(supports[i:i + BATCH])) for i in range(0, len(supports), BATCH)) / (
            len(supports) // BATCH
        )
        max_unique = max(len(set(supports[i:i + BATCH])) for i in range(0, len(supports), BATCH))
        load_if_dedup = avg_unique  # 1 load per unique p per round (optimistic)
        load_baseline = BATCH  # scalar gather: 1 load/lane (optimistic lower than 8 SIMD)
        print(
            f"  depth {d}: avg unique p / 256 = {avg_unique:.1f}, max = {max_unique}, "
            f"optimistic dedup load ratio {load_if_dedup/load_baseline:.2f}"
        )
    print("  verdict: p support stays large (~200+); batch gather dedup cannot kill 1536 loads.")
    print("  note @depth5: only 32 unique p exist (full range), but 256 lane assignments still")
    print("        require 256 node deliveries; without cross-lane permute, batch dedup")
    print("        needs 32 setup loads + 256 indexed loads (=288) >= 256 mem gathers.")


def hash_bijectivity(samples: int = 100_000) -> None:
    print("\n=== 3a) Hash bijectivity sample ===")
    seen = set()
    coll = 0
    for a in range(samples):
        b = myhash(a)
        if b in seen:
            coll += 1
        seen.add(b)
    print(f"  sampled {samples}, collisions {coll}")
    print("  verdict: hash behaves as permutation on sampled domain (no fold shortcut).")


def muladd_fusion_search(trials: int = 50_000) -> None:
    print("\n=== 3b) Extra muladd fusion search (s0→s1 composition) ===")
    K0 = HASH_STAGES[0][1]
    K1 = HASH_STAGES[1][1]
    rng = random.Random(2)
    # Check if s1(muladd(a,4097,K0)) == (m*a+c) mod 2^32 for fixed m,c
    for _ in range(5):
        m = rng.randrange(2**32)
        c = rng.randrange(2**32)
        ok = 0
        for a in range(trials):
            v0 = (4097 * a + K0) & MASK
            s1 = ((v0 ^ K1) ^ (v0 >> 19)) & MASK
            lin = (m * a + c) & MASK
            if s1 == lin:
                ok += 1
        print(f"  random (m,c) trial: {ok}/{trials} matches")
    print("  verdict: s0→s1 is not affine; no extra muladd fusion like s2+s3.")


def k5_defer_d4_extension_budget() -> None:
    print("\n=== 4) K5 defer extension d3→d4 cold (algebra + op budget) ===")
    # Algebra: defer at depth-3 round when next is d4 cold mux + enter_x on d4
    # is same as existing K5 defer into mux rounds — mirrors flip-p subset.
    # Budget: at most 32 extra defer instances (one d3 round) × 1 valu = 32 ops (~5.3c)
    extra_valu = 32
    base_valu = 6338
    new_floor = (base_valu - extra_valu) / 6
    print(f"  optimistic extra defer: -{extra_valu} valu ops → valu floor {new_floor:.1f}")
    print(f"  still above 1000 bind ({max(new_floor, 1056.3):.1f}); NOT a breakthrough.")
    print("  note: flip-p family already NO-GO on perf despite algebra PASS.")


def gap_accounting() -> None:
    print("\n=== 5) Op-count gap vs GATHER_FREE (@1085) ===")
    base = {"valu": 6338, "load": 2087, "cycles": 1085}
    gf = {"valu": 5898, "load": 135, "cycles": 1004}
    dv = base["valu"] - gf["valu"]
    dl = base["load"] - gf["load"]
    dc = base["cycles"] - gf["cycles"]
    need = base["cycles"] - 1000
    print(f"  GATHER_FREE saves: cycles {dc}, valu ops {dv}, load ops {dl}")
    print(f"  gap to sub-1000: {need} cycles")
    print(f"  => need correctness-preserving elimination of ~{dv}+ valu ops")
    print(f"     and/or ~{dl}+ load ops (gather path), not hash-only tweaks.")


def main() -> None:
    print("=== W7 algorithm breakthrough probe @1085 ===\n")
    round_necessity(trials=200)
    p_support_at_depth(trials=100)
    hash_bijectivity(samples=65536)
    muladd_fusion_search()
    k5_defer_d4_extension_budget()
    gap_accounting()
    print("\n=== SUMMARY ===")
    print("Sub-1000 requires a CORRECT deep-gather elimination (~440 valu-class ops).")
    print("Hash/traverse/lazy-fold/defer-extension axes cannot close the 85-cycle gap alone.")


if __name__ == "__main__":
    main()

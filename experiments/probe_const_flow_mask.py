#!/usr/bin/env python3
"""Decisive const_flow_mask exploration: bit-count sweep + multi-restart SA.

Complements anneal_const_flow_mask.py. Two probes:
  (1) N-sweep: for total hot-bits N in 6..20, greedily build the best N-hot mask
      (start empty, add the single best const to flow, repeat N times) and also
      test N random restarts. Re-checks the N>12 serialization claim.
  (2) multi-restart SA from random seeds to escape the champ basin.

Cycle count == len(kb.instrs) with the winning rotation pinned (rot 27).
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import perf_takehome  # noqa: E402

MASK_LEN = 58
PIN_ROT = 27
CHAMP = [1, 1, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0, 1,
         1, 0, 0, 1] + [0] * 32

# n_nodes / n_idx for the shipped config (10, *, *, 16).
from tests.frozen_problem import Tree, Input  # noqa: E402
_F = Tree.generate(10)
_I = Input.generate(_F, 256, 16)
_NN, _NI = len(_F.values), len(_I.indices)

_cache = {}


def ev(mask):
    key = tuple(mask)
    if key in _cache:
        return _cache[key]
    os.environ["CONST_FLOW_MASK"] = json.dumps([int(b) for b in mask])
    kb = perf_takehome.KernelBuilder()
    kb._rotations = [PIN_ROT]
    kb.build_kernel(10, _NN, _NI, 16)
    c = len(kb.instrs)
    _cache[key] = c
    return c


def greedy_build(target_n):
    """Greedily add the const that most reduces cycles, up to target_n hot bits."""
    mask = [0] * MASK_LEN
    for _ in range(target_n):
        best_i, best_c = None, None
        for i in range(MASK_LEN):
            if mask[i]:
                continue
            mask[i] = 1
            c = ev(mask)
            mask[i] = 0
            if best_c is None or c < best_c:
                best_c, best_i = c, i
        if best_i is None:
            break
        mask[best_i] = 1
    return mask, ev(mask)


def main():
    base = ev(CHAMP)
    print(f"champ (11-hot) cycles={base}", flush=True)

    # (1) greedy N-sweep
    print("\n=== greedy N-sweep ===", flush=True)
    best_overall, best_overall_c = list(CHAMP), base
    for n in range(6, 21):
        m, c = greedy_build(n)
        tag = ""
        if c < best_overall_c:
            best_overall, best_overall_c = list(m), c
            tag = "  <== NEW BEST"
        print(f"  N={n:2d} greedy cycles={c}{tag}", flush=True)

    # (2) random-restart hill climb (bit flips, accept improve/equal)
    print("\n=== random-restart hill climb ===", flush=True)
    random.seed(7)
    for restart in range(8):
        n0 = random.randint(6, 16)
        idx = random.sample(range(MASK_LEN), n0)
        m = [0] * MASK_LEN
        for i in idx:
            m[i] = 1
        c = ev(m)
        improved = True
        while improved:
            improved = False
            order = list(range(MASK_LEN))
            random.shuffle(order)
            for i in order:
                m[i] ^= 1
                cc = ev(m)
                if cc < c:
                    c = cc
                    improved = True
                else:
                    m[i] ^= 1
        if c < best_overall_c:
            best_overall, best_overall_c = list(m), c
            print(f"  restart {restart} n0={n0} cycles={c}  <== NEW BEST "
                  f"mask={json.dumps(m)}", flush=True)
        else:
            print(f"  restart {restart} n0={n0} cycles={c} bits={sum(m)}",
                  flush=True)

    print(f"\nBEST cycles={best_overall_c} bits={sum(best_overall)} "
          f"evals={len(_cache)}")
    print(f"BEST_MASK={json.dumps([int(b) for b in best_overall])}")


if __name__ == "__main__":
    main()

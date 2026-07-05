#!/usr/bin/env python3
"""SA over the 58-bit _const_flow_mask (const->flow routing gene).

Cycle count is a static property of the VLIW schedule (kb.instrs) and the
machine, independent of the random forest data. So we build the kernel once
per mask, run the machine once on a fixed image, and read machine.cycle.

Seed = current 1151 champ mask. Moves: flip 1-2 bits, occasional swap. Also
probes total hot-bit counts N=8..16. Accept strict improvements; SA with a
cooling schedule to escape the 1151 plateau.

Usage:
    python anneal_const_flow_mask.py [iters]
Prints the best mask (JSON) and its cycle count.
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tests"))

from tests.frozen_problem import (  # noqa: E402
    Machine, build_mem_image, Tree, Input, N_CORES,
)

CHAMP = [1, 1, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0, 1,
         1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
         0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
MASK_LEN = 58

# One fixed forest/input for schedule evaluation (cycle count is data-independent).
_FOREST = Tree.generate(10)
_INP = Input.generate(_FOREST, 256, 16)
_MEM = build_mem_image(_FOREST, _INP)
_N_NODES = len(_FOREST.values)
_N_IDX = len(_INP.indices)


# Winning rotation for the current schedule (see sweep: rot 27 = 1151, next 1159).
# Cycle count == len(kb.instrs); pin the winning rotation for a ~0.28s eval.
# Any improvement is re-validated with the full K-rotation sweep before shipping.
PIN_ROT = 27

import perf_takehome  # noqa: E402


def eval_mask(mask, rotations=(PIN_ROT,)):
    """Build the kernel with this mask; return schedule length (== cycle count)."""
    os.environ["CONST_FLOW_MASK"] = json.dumps([int(b) for b in mask])
    kb = perf_takehome.KernelBuilder()
    kb._rotations = list(rotations)
    kb.build_kernel(10, _N_NODES, _N_IDX, 16)
    return len(kb.instrs)


def main():
    iters = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    random.seed(1234)

    cur = list(CHAMP)
    cur_c = eval_mask(cur)
    best, best_c = list(cur), cur_c
    print(f"seed champ cycles={cur_c} bits={sum(cur)}", flush=True)

    import math
    T0, T1 = 2.0, 0.05
    seen = {}
    for it in range(iters):
        T = T0 * (T1 / T0) ** (it / max(1, iters - 1))
        cand = list(cur)
        r = random.random()
        if r < 0.55:  # flip 1 bit
            i = random.randrange(MASK_LEN)
            cand[i] ^= 1
        elif r < 0.80:  # flip 2 bits
            for _ in range(2):
                cand[random.randrange(MASK_LEN)] ^= 1
        else:  # swap a hot and a cold bit (keep count, repack which consts)
            hot = [i for i, b in enumerate(cand) if b]
            cold = [i for i, b in enumerate(cand) if not b]
            if hot and cold:
                cand[random.choice(hot)] = 0
                cand[random.choice(cold)] = 1
        key = tuple(cand)
        if key in seen:
            cc = seen[key]
        else:
            cc = eval_mask(cand)
            seen[key] = cc
        d = cc - cur_c
        if d <= 0 or random.random() < math.exp(-d / T):
            cur, cur_c = cand, cc
        if cc < best_c:
            best, best_c = list(cand), cc
            print(f"  it={it} NEW BEST cycles={cc} bits={sum(cand)} "
                  f"mask={json.dumps([int(b) for b in cand])}", flush=True)
        if it % 250 == 0:
            print(f"  it={it} T={T:.3f} cur={cur_c} best={best_c} "
                  f"evals={len(seen)}", flush=True)

    print(f"\nBEST cycles={best_c} bits={sum(best)}")
    print(f"BEST_MASK={json.dumps([int(b) for b in best])}")


if __name__ == "__main__":
    main()

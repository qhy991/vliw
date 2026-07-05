"""#12 p-space: verify traverse algebra vs reference before kernel edits."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
from problem import HASH_STAGES, myhash, Tree, Input, build_mem_image, reference_kernel2

K5 = HASH_STAGES[5][1]
MASK = (1 << 32) - 1
DEFER = {0, 1, 2, 10, 11, 12, 13}
H1 = 11
FH = 10
N_NODES = 2047


def myhash_x(a):
    fns = {"+": lambda x, y: x + y, "^": lambda x, y: x ^ y,
           "<<": lambda x, y: x << y, ">>": lambda x, y: x >> y}
    r = lambda x: x & MASK
    for i, (op1, val1, op2, op3, val3) in enumerate(HASH_STAGES):
        if i == 5:
            a = r(a ^ r(fns[op3](a, val3)))
        else:
            a = r(fns[op2](r(fns[op1](a, val1)), r(fns[op3](a, val3))))
    return a


def ref_traverse(idx, rem, depth, defer_x, skip, fh):
    """Reference idx-space traverse (current kernel)."""
    if skip:
        return idx
    if defer_x:
        if depth == 0:
            idx = 2 - rem
        else:
            idx = 2 * idx + (2 - rem)
    elif depth == 0:
        idx = 1 + rem
    else:
        idx = 2 * idx + (1 + rem)
    if depth == fh:
        idx = 0 if idx >= N_NODES else idx
    return idx


def p_traverse(p, rem, depth, defer_x, skip):
    """p-space traverse per directions/12-pspace-traverse.md §4."""
    if skip:
        return p
    if defer_x:
        rem_true = rem ^ 1
        if depth == 0:
            p = 1 - rem  # rem_x; 1 - rem_x
        else:
            p = 2 * p + rem_true
    elif depth == 0:
        p = rem
    else:
        p = 2 * p + rem
    return p


def idx_from_p(p, depth):
    return (1 << depth) - 1 + p


def run_trace(n=50000):
    random.seed(42)
    bad_p = bad_idx = bad_inv = 0
    for _ in range(n):
        p = 0
        idx = 0
        val = random.randint(0, MASK)
        for r in range(16):
            depth = r % H1
            defer = r in DEFER and r != 15 and (r + 1) % H1 < 4
            skip = (r == 15) or ((r + 1) % H1 == 0)
            enter_x = r > 0 and (r - 1) in DEFER and (r - 1) != 15 and (r % H1) < 4

            inp = (val ^ (0 if depth == 0 else 0)) & MASK  # skip node for traverse test
            val = myhash_x(inp) if defer else myhash(inp)
            rem = val % 2
            rem_x = rem ^ 1 if enter_x else rem

            idx_new = ref_traverse(idx, rem_x if defer else rem, depth, defer, skip, FH)
            p_new = p_traverse(p, rem_x if defer else rem, depth, defer, skip)

            if not skip:
                if idx_new != idx_from_p(p_new, depth if depth < FH or depth == FH else 0):
                    # after wrap at fh, p resets to 0 at next d0
                    if depth != FH:
                        bad_inv += 1
                p = p_new
                idx = idx_new
            if depth == FH:
                p = 0
            if depth == 10 and not skip:
                p = 0  # round 11 d0 reset
    print(f"p-space traverse vs idx invariant: {bad_inv} violations / {n} traces")
    return bad_inv == 0


def run_full_kernel(n_elem=256):
    """Cross-check p invariant on reference_kernel2 traces."""
    f = Tree.generate(FH)
    inp = Input.generate(f, n_elem, 16)
    mem = build_mem_image(f, inp)
    tr = {}
    for _ in reference_kernel2(mem, tr):
        pass
    bad = 0
    for i in range(n_elem):
        p = 0
        for r in range(16):
            d = r % H1
            idx = tr[(r, i, "idx")]
            if idx != idx_from_p(p, d):
                bad += 1
            rem = tr[(r, i, "hashed_val")] & 1
            p = 0 if d == FH else (2 * p + rem)
    print(f"reference_kernel2 idx==2^d-1+p: {bad} / {n_elem * 16}")
    return bad == 0


if __name__ == "__main__":
    ok1 = run_trace()
    ok2 = run_full_kernel()
    print("ALL-PASS" if ok1 and ok2 else "FAIL")

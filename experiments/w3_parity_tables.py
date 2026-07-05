"""#03 phase-2: verify re-permuted parity tables for d2/d3 node lookup."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
from problem import Tree, Input, build_mem_image, reference_kernel2

FH = 10
H1 = 11


def parity_accum(rem_history):
    """p from rem list (oldest first)."""
    p = 0
    for rem in rem_history:
        p = 2 * p + rem
    return p


def build_d2_table(tree):
    """tree[2^2-1+p] for p in 0..3 maps to idx 3..6."""
    return [tree[3 + p] for p in range(4)]


def build_d3_table(tree):
    """tree[2^3-1+p] for p in 0..7 maps to idx 7..14."""
    return [tree[7 + p] for p in range(8)]


def mux_d2(p, table):
    """4-way mux keyed on parity bits p (0..3), not idx low bits."""
    return table[p]


def mux_d3(p, table):
    return table[p]


def verify_traces(n_elem=256):
    f = Tree.generate(FH)
    inp = Input.generate(f, n_elem, 16)
    mem = build_mem_image(f, inp)
    tr = {}
    for _ in reference_kernel2(mem, tr):
        pass

    bad_d2 = bad_d3 = 0
    for i in range(n_elem):
        rems = []
        for r in range(16):
            d = r % H1
            rem = tr[(r, i, "hashed_val")] & 1
            node_ref = tr[(r, i, "node_val")]
            if d == 2:
                p = parity_accum(rems)
                node_p = mux_d2(p, build_d2_table(f.values))
                if node_ref != node_p:
                    bad_d2 += 1
            elif d == 3:
                p = parity_accum(rems)
                node_p = mux_d3(p, build_d3_table(f.values))
                if node_ref != node_p:
                    bad_d3 += 1
            rems.append(rem)
            if d == FH:
                rems = []
            if d == 10:
                rems = []

    print(f"d2 parity-table lookup: {bad_d2} mismatches / {n_elem * 2}")
    print(f"d3 parity-table lookup: {bad_d3} mismatches / {n_elem * 2}")
    return bad_d2 == 0 and bad_d3 == 0


def verify_bijection():
    """Confirm p -> idx mapping is bijective on each depth range."""
    for d in (2, 3):
        base = (1 << d) - 1
        n = 1 << d
        idxs = [base + p for p in range(n)]
        assert len(set(idxs)) == n
        print(f"depth {d}: p in 0..{n-1} -> idx {min(idxs)}..{max(idxs)} bijection OK")


if __name__ == "__main__":
    verify_bijection()
    ok = verify_traces()
    print("ALL-PASS" if ok else "FAIL — need rem history not just single-step p")

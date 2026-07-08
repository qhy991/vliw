"""Algebra kill-test for the flipped-p (p-tilde) traverse scheme (Wave-7).

Claim: on the p-space graph, every K5-deferring mux round at depth>=1 can
emit its traverse as a SINGLE muladd  p~' = 2*p~ + rem_x  (instead of the
2-op  muladd + sub), accumulating a compile-time-constant XOR mask
M_d = 2^d - 1 on p.  Consumers absorb M for free:
  - mux rounds (d1/d2/d3, d4-cold): swapped vselect branch order,
  - d4 gather rounds (r4, r15): a 16-word shadow row in free memory,
        shadow4[i] = tree[15 + (i ^ 15)] ^ K5  ( = tree[30-i] ^ K5 ),
    which also lets r3/r14 defer K5 across the d4 boundary,
  - d3 gather instances (sparse mask) likewise via an 8-word shadow row,
  - r4 pays one correction op  p4 = p~4 ^ 15  before its true-space traverse
    (r15 needs none: skip_idx_update).

This probe simulates the EXACT emitted arithmetic (x-format vals, rem_x
traverses, shadow-table reads, swapped-branch muxes modeled as index
correction) for all 256 elements x 16 rounds and compares the final values
bit-exactly against reference_kernel.  PASS = safe to implement.
"""
import random
import sys
sys.path.insert(0, ".")
from problem import Tree, Input, reference_kernel, HASH_STAGES

K5 = 0xB55A4F09
M32 = (1 << 32) - 1


def hash_stages_04(a):
    """Stages 0..4 of myhash (everything before the final xorshift stage)."""
    for op1, val1, op2, op3, val3 in HASH_STAGES[:5]:
        fns = {"+": lambda x, y: (x + y) & M32, "^": lambda x, y: x ^ y,
               "<<": lambda x, y: (x << y) & M32, ">>": lambda x, y: x >> y}
        a = fns[op2](fns[op1](a, val1), fns[op3](a, val3)) & M32
    return a


def stage5(a, defer):
    m = a ^ (a >> 16)
    return m if defer else (m ^ K5)


def run_scheme(tree_vals, values, rounds, fh):
    h1 = fh + 1
    n_final = []
    # shadow tables (built once at setup by store engine in the real kernel)
    shadow4 = [tree_vals[15 + (i ^ 15)] ^ K5 for i in range(16)]
    shadow3 = [tree_vals[7 + (i ^ 7)] ^ K5 for i in range(8)]
    for e, v0 in enumerate(values):
        v = v0          # may be x-format (trueval ^ K5) after a defer round
        pt = 0          # p~ (flipped p) or true p depending on depth regime
        for r in range(rounds):
            d = r % h1
            skip = (r == rounds - 1) or ((r + 1) % h1 == 0)
            # NEW defer condition: successor depth <= 4 absorbs K5
            defer = (r != rounds - 1) and ((r + 1) % h1 <= 4)
            enter_x = (r > 0) and ((r - 1) != rounds - 1) and ((r % h1) <= 4)
            # ---- node fetch ----
            if d == 0:
                node = tree_vals[0] ^ (K5 if enter_x else 0)
            elif 1 <= d <= 3:
                # mux (or d3 shadow gather -- same value either way):
                # swapped branches == reading index pt ^ (2^d - 1)
                M = (1 << d) - 1
                p_true = pt ^ M
                node = tree_vals[(1 << d) - 1 + p_true] ^ (K5 if enter_x else 0)
                if d == 3:
                    assert node == shadow3[pt] ^ (0 if enter_x else K5)
            elif d == 4:
                # r4 / r15: gather from the reversed shadow row via p~4
                assert enter_x, "d4 must be enter_x in the flip scheme"
                node = shadow4[pt]
                assert node == tree_vals[15 + (pt ^ 15)] ^ K5
            else:
                node = tree_vals[(1 << d) - 1 + pt]   # true p-space, true tree
            # ---- hash ----
            x = (v ^ node) & M32
            a = hash_stages_04(x)
            v = stage5(a, defer)
            rem = v & 1        # rem_x if defer else rem_true
            # ---- traverse ----
            if skip:
                pass
            elif defer:
                if d == 0:
                    pt = rem                      # p~1 = rem_x   (M=1)
                else:
                    pt = 2 * pt + rem             # p~' = 2p~ + rem_x
            else:
                if d == 4:
                    p4 = pt ^ 15                  # correction (+1 op at r4)
                    pt = 2 * p4 + rem
                else:
                    pt = 2 * pt + rem             # true deep p-space
        n_final.append(v)
    return n_final


def main():
    random.seed(0)
    for trial in range(20):
        fh, rounds, bs = 10, 16, 256
        t = Tree.generate(fh)
        inp = Input.generate(t, bs, rounds)
        vals_ref = list(inp.values)
        got = run_scheme(t.values, list(inp.values), rounds, fh)
        reference_kernel(t, inp)
        assert got == inp.values, f"trial {trial}: MISMATCH"
        # keep RNG stream moving
        inp.values = vals_ref
    print("flip-p algebra: PASS (20 trials x 256 elements, bit-exact)")


if __name__ == "__main__":
    main()

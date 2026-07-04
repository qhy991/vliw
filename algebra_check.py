"""
Standalone algebra harness for the stage-5 K5-deferral (x-space carry).

R3 mitigation (see DIRECTION.md §5): before touching the kernel, prove the full
multi-round recursion is bit-exact vs the reference for the EXACT per-round
control flow (depth-specialized node source + idx update + skip + defer + parity
swap) the kernel implements.

Run: python algebra_check.py    (from the worktree dir)
Must print ALL-PASS with 0 mismatches.
"""
import random
from problem import HASH_STAGES, myhash

K5 = HASH_STAGES[5][1]
MASK = (1 << 32) - 1


def myhash_x(a):
    """The 6-stage hash with the FINAL ^K5 removed. myhash_x(x) == myhash(x) ^ K5."""
    fns = {
        "+": lambda x, y: x + y, "^": lambda x, y: x ^ y,
        "<<": lambda x, y: x << y, ">>": lambda x, y: x >> y,
    }
    r = lambda x: x & MASK
    for i, (op1, val1, op2, op3, val3) in enumerate(HASH_STAGES):
        if i == 5:
            a = r(a ^ r(fns[op3](a, val3)))      # drop the ^K5
        else:
            a = r(fns[op2](r(fns[op1](a, val1)), r(fns[op3](a, val3))))
    return a


def node_for_depth(depth, idx, tree, forest_height):
    """Mirror the kernel's node source per depth (structural invariant: at this
    round every element is at `depth`, so idx is in the expected range)."""
    if depth == 0:
        return tree[0]                       # kernel: nb0 broadcast (idx==0)
    elif depth == 1:
        return tree[1] if (idx & 1) else tree[2]   # kernel: vselect(idx&1, nb1, nb2)
    else:
        return tree[idx]                     # depth>=2 mux/gather, idx exact


def ref_round(idx, val, tree, n_nodes, forest_height, depth):
    """Faithful reference round (problem.py semantics), depth-aware node."""
    node = node_for_depth(depth, idx, tree, forest_height)
    val = myhash((val ^ node) & MASK)
    idx = 2 * idx + (1 if val % 2 == 0 else 2)
    idx = 0 if idx >= n_nodes else idx
    return idx, val


def x_round(idx, val, tree, n_nodes, forest_height, depth,
            defer, skip, enter_x):
    """
    One x-space kernel round, mirroring _emit_vec_round exactly.
      enter_x : incoming `val` is trueval^K5 (broadcasts carry node^K5 this round)
      defer   : this round emits stage-5 x-variant (trailing ^K5 deferred)
      skip    : traverse/idx update skipped (bottom round; next is depth 0)
    Returns (next_idx, val_out, val_out_is_x).
    """
    node = node_for_depth(depth, idx, tree, forest_height)
    node_used = (node ^ K5) & MASK if enter_x else node
    inp = (val ^ node_used) & MASK           # == trueval ^ node (K5 cancels if enter_x)
    val = myhash_x(inp) if defer else myhash(inp)
    val_out_is_x = defer
    if not skip:
        rem = val % 2
        if depth == 0:
            # depth-0 constant-fold: idx==0 so 2*idx+addend == addend.
            idx = (2 - rem) if val_out_is_x else (1 + rem)
        else:
            addend = (2 - rem) if val_out_is_x else (1 + rem)
            idx = 2 * idx + addend
        if depth == forest_height:
            idx = 0 if idx >= n_nodes else idx
    return idx, val, val_out_is_x


def run_config(forest_height, rounds, seed):
    random.seed(seed)
    h1 = forest_height + 1
    n_nodes = 2 ** (forest_height + 1) - 1
    tree = [random.randint(0, 2 ** 30 - 1) for _ in range(n_nodes)]

    defer = [(r != rounds - 1) and ((r + 1) % h1 < 4) for r in range(rounds)]
    skip = [(r == rounds - 1) or ((r + 1) % h1 == 0) for r in range(rounds)]
    enter_x = [(r > 0 and defer[r - 1]) for r in range(rounds)]

    mism = 0
    for _ in range(400):
        v0 = random.randint(0, 2 ** 30 - 1)
        r_idx, r_val = 0, v0
        x_idx, x_val, x_is_x = 0, v0, False
        for r in range(rounds):
            depth = r % h1
            r_idx, r_val = ref_round(r_idx, r_val, tree, n_nodes, forest_height, depth)
            x_idx, x_val, x_is_x = x_round(
                x_idx, x_val, tree, n_nodes, forest_height, depth,
                defer[r], skip[r], enter_x[r])
            decoded = (x_val ^ K5) & MASK if x_is_x else x_val
            if decoded != r_val:
                mism += 1
                if mism <= 3:
                    print(f"  VAL mismatch r={r} d={depth} ref={r_val:#x} "
                          f"got={decoded:#x} (x={x_is_x})")
            # idx compared only when the kernel maintains it this round
            if not skip[r] and x_idx != r_idx:
                mism += 1
                if mism <= 3:
                    print(f"  IDX mismatch r={r} d={depth} ref={r_idx} got={x_idx}")
    return mism, defer, skip, enter_x


def main():
    random.seed(1)
    for _ in range(300_000):
        x = random.randint(0, MASK)
        assert myhash_x(x) == (myhash(x) ^ K5), "myhash_x identity broken"
    print("myhash_x(x) == myhash(x) ^ K5  : PASS (300k random)")

    total = 0
    configs = [(10, 16), (10, 16), (4, 16), (4, 22), (3, 20), (10, 33), (2, 30), (10, 11)]
    for fh, rounds in configs:
        sub = 0
        for seed in range(6):
            m, defer, skip, enter_x = run_config(fh, rounds, seed)
            sub += m
        total += sub
        print(f"fh={fh:2d} rounds={rounds:2d}: mism={sub:4d}  "
              f"defer={[r for r in range(rounds) if defer[r]]}  "
              f"swap={[r for r in range(rounds) if defer[r] and not skip[r]]}")
    print()
    if total == 0:
        print("ALL-PASS: 0 mismatches across all configs. x-space carry is bit-exact.")
    else:
        print(f"FAIL: {total} mismatches.")
    return total


if __name__ == "__main__":
    import sys
    sys.exit(1 if main() else 0)

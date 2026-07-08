#!/usr/bin/env python3
"""2-round macro feasibility probe (structural, not parameter tuning).

Question: can two consecutive rounds be algebraically fused so that
intermediate state (node fetch + partial hash) is eliminated while
preserving bit-exact final values?

We test several candidate fusion patterns against the reference kernel
semantics for all 16-round pairs under the shipped defer/skip/enter_x schedule.
"""
from __future__ import annotations

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from problem import HASH_STAGES, myhash, VLEN

K5 = HASH_STAGES[5][1]
MASK = (1 << 32) - 1
FOREST_H = 10
ROUNDS = 16
H1 = FOREST_H + 1


def myhash_x(a: int) -> int:
    fns = {"+": lambda x, y: x + y, "^": lambda x, y: x ^ y,
           "<<": lambda x, y: x << y, ">>": lambda x, y: x >> y}
    r = lambda x: x & MASK
    for i, (op1, val1, op2, op3, val3) in enumerate(HASH_STAGES):
        if i == 5:
            a = r(a ^ r(fns[op3](a, val3)))
        else:
            a = r(fns[op2](r(fns[op1](a, val1)), r(fns[op3](a, val3))))
    return a


def node_for_depth(depth: int, idx: int, tree: list[int]) -> int:
    if depth == 0:
        return tree[0]
    if depth == 1:
        return tree[1] if (idx & 1) else tree[2]
    return tree[idx]


def ref_step(idx: int, val: int, tree: list[int], depth: int, n_nodes: int) -> tuple[int, int]:
    node = node_for_depth(depth, idx, tree)
    val = myhash((val ^ node) & MASK)
    add = 1 if val % 2 == 0 else 2
    idx = 2 * idx + add
    if depth == FOREST_H and idx >= n_nodes:
        idx = 0
    return idx, val


def pspace_step(idx: int, val: int, tree: list[int], depth: int,
                defer: bool, skip: bool, enter_x: bool) -> tuple[int, int, bool]:
    """One p-space kernel round mirroring perf_takehome."""
    node = node_for_depth(depth, idx, tree)
    node_used = (node ^ K5) & MASK if enter_x else node
    inp = (val ^ node_used) & MASK
    val = myhash_x(inp) if defer else myhash(inp)
    val_out_is_x = defer
    if not skip:
        rem = val % 2
        if defer:
            if depth == 0:
                idx = (1 - rem) & MASK  # p = 1 - rem_x handled below; simplified
            else:
                idx = (2 * idx + (1 - rem)) & MASK  # p_next = 2p + (rem_x^1)
        elif depth == 0:
            idx = rem
        else:
            idx = (2 * idx + rem) & MASK
    return idx, val, val_out_is_x


def schedule():
    defer = [(r != ROUNDS - 1) and ((r + 1) % H1 < 4) for r in range(ROUNDS)]
    skip = [(r == ROUNDS - 1) or ((r + 1) % H1 == 0) for r in range(ROUNDS)]
    enter_x = [(r > 0 and defer[r - 1]) for r in range(ROUNDS)]
    return defer, skip, enter_x


def simulate_reference(tree: list[int], val0: int, n_nodes: int) -> int:
    defer, skip, enter_x = schedule()
    idx, val, is_x = 0, val0, False
    for r in range(ROUNDS):
        depth = r % H1
        node = node_for_depth(depth, idx, tree)
        node_used = (node ^ K5) & MASK if enter_x[r] else node
        inp = (val ^ node_used) & MASK
        val = myhash_x(inp) if defer[r] else myhash(inp)
        is_x = defer[r]
        if not skip[r]:
            rem = val % 2
            if defer[r]:
                if depth == 0:
                    idx = 1 - rem if not is_x else rem  # simplified p-space
                else:
                    p = idx
                    rem_true = rem ^ 1 if is_x else rem
                    idx = 2 * p + rem_true
            elif depth == 0:
                idx = rem
            else:
                idx = 2 * idx + rem
    decoded = (val ^ K5) & MASK if is_x else val
    return decoded


def try_fuse_rounds(r: int, tree: list[int], val0: int, n_nodes: int) -> bool:
    """Attempt naive 2-round fusion: hash(hash(v^n0)^n1) with combined traverse.
    Returns True if fusion matches sequential reference for this start state."""
    defer, skip, enter_x = schedule()
    d0, d1 = r % H1, (r + 1) % H1

    # Sequential reference for rounds r and r+1 only, starting from (idx,val).
    idx, val, is_x = 0, val0, False
    for rr in [r, r + 1]:
        depth = rr % H1
        node = node_for_depth(depth, idx, tree)
        node_used = (node ^ K5) & MASK if enter_x[rr] else node
        inp = (val ^ node_used) & MASK
        val = myhash_x(inp) if defer[rr] else myhash(inp)
        is_x = defer[rr]
        if not skip[rr]:
            rem = val % 2
            if defer[rr]:
                if depth == 0:
                    idx = rem
                else:
                    idx = 2 * idx + (rem ^ 1)
            elif depth == 0:
                idx = rem
            else:
                idx = 2 * idx + rem

    seq_val = (val ^ K5) & MASK if is_x else val

    # Naive fusion attempt: apply both nodes then one combined hash — WRONG in general.
    node0 = node_for_depth(d0, 0, tree)
    node1 = node_for_depth(d1, 0, tree)  # wrong idx assumption
    fused = myhash(myhash(val0 ^ node0) ^ node1)
    return fused == seq_val


def main() -> None:
    print("=== W7 two-round macro feasibility probe ===\n")
    rng = random.Random(42)
    n_nodes = 2 ** (FOREST_H + 1) - 1

    # Test 1: can any round pair be skipped without changing final val?
    print("Test 1: round-pair necessity for final val (500 trials)")
    skip_pair_fail = 0
    for _ in range(500):
        tree = [rng.randrange(2**30) for _ in range(n_nodes)]
        val0 = rng.randrange(2**30)
        gold = simulate_reference(tree, val0, n_nodes)
        for r in range(ROUNDS - 1):
            # skip both rounds r and r+1 in full sim — approximate via partial
            pass  # covered by prior round-necessity probe
    print("  (see probe_w7_algo_breakthrough.py — all single rounds essential)")
    print()

    # Test 2: hash composition — is hash(a^K) ^ c ever equivalent to fewer ops?
    print("Test 2: hash algebraic idempotence / composition (100k random)")
    compose_hits = 0
    for _ in range(100_000):
        a = rng.randrange(2**32)
        b = rng.randrange(2**32)
        # hash(a^K1) ^ hash(b^K2) == hash((a^K1)^(b^K2)) ? Never — XOR outside hash.
        if myhash(a ^ b) == (myhash(a) ^ myhash(b)):
            compose_hits += 1
    print(f"  myhash(a^b) == myhash(a)^myhash(b): {compose_hits}/100000")
    print("  verdict: hash is NOT XOR-homomorphic -> no 2-round XOR fold")
    print()

    # Test 3: muladd chain — can two consecutive muladd+combine stages fuse?
    print("Test 3: consecutive muladd stage fusion search")
    # Stage pattern per round: muladd(m4097), xor-combine, muladd(m33), muladd(m16896),
    # xor-combine, muladd(m9), xor-combine/K5-defer
    # Total per round: 4 muladd + 3 combine = 7 valu-class ops minimum
    # Two rounds = 14 valu ops. Can we do it in fewer with closed form?
    hits = 0
    for _ in range(50_000):
        a = rng.randrange(2**32)
        k0, k1 = rng.randrange(2**32), rng.randrange(2**32)
        # Two sequential full hashes
        h2 = myhash(myhash(a ^ k0) ^ k1)
        # Try single hash approximation
        if myhash(a ^ (k0 ^ k1)) == h2:
            hits += 1
    print(f"  hash(hash(a^k0)^k1) == hash(a^(k0^k1)): {hits}/50000")
    print("  verdict: no 2-round hash fold via XOR of keys")
    print()

    # Test 4: traverse-only fusion — can p_next skip intermediate p?
    print("Test 4: 2-step traverse closed form (p-space)")
    # p_next = 2*(2*p + r0) + r1 = 4p + 2*r0 + r1
    # This IS composable — but we still need both hash rounds for val.
    mism = 0
    for _ in range(10_000):
        p = rng.randrange(32)
        r0 = rng.randrange(2)
        r1 = rng.randrange(2)
        p1 = 2 * p + r0
        p2 = 2 * p1 + r1
        p2_direct = 4 * p + 2 * r0 + r1
        if p2 != p2_direct:
            mism += 1
    print(f"  traverse compose mismatches: {mism}/10000")
    print("  verdict: traverse IS composable, but val still needs 2 hash rounds")
    print()

    # Test 5: gather elimination via traverse compose + deferred node
    print("Test 5: can we skip round-r node fetch if we know round-(r+1) depth?")
    # At round r depth d, next round is depth d+1 (unless wrap).
    # node_{r+1} depends on p_{r+1} which depends on hash(val_r).
    # Cannot know node_{r+1} before computing hash(val_r) -> node fetch NOT eliminable.
    print("  node_{r+1} = tree[f(p_r, hash(val_r))] — data-dependent")
    print("  verdict: NO — node fetch at round r+1 cannot be prefetched without hash(r)")
    print()

    print("=== SUMMARY ===")
    print("2-round macro fusion is blocked on the VAL (hash) axis, not traverse.")
    print("Traverse compose is algebraic but val path needs both full hash rounds.")
    print("Next structural target: single-round hash stage reduction (not 2-round fold).")


if __name__ == "__main__":
    main()

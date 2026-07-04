"""Verify parity-carry node lookup matches reference on shallow rounds."""
import random
from problem import Tree, Input, build_mem_image, reference_kernel2

random.seed(7)
f = Tree.generate(10)
inp = Input.generate(f, 256, 16)
mem = build_mem_image(f, inp)
tr = {}
for _ in reference_kernel2(mem, tr):
    pass

h1 = 11
bad_inv = 0
bad_node = 0
for i in range(256):
    p = 0
    for r in range(16):
        d = r % h1
        idx = tr[(r, i, "idx")]
        if idx != (1 << d) - 1 + p:
            bad_inv += 1
        rem = tr[(r, i, "hashed_val")] & 1
        if d == 1:
            # parity-carry depth-1: rem_prev is rem from round r-1
            rem_prev = tr[(r - 1, i, "hashed_val")] & 1 if r > 0 else 0
            if r == 11:
                rem_prev = 0  # wrap reset
            node_ref = tr[(r, i, "node_val")]
            node_p = f.values[1 + rem_prev]
            if node_ref != node_p:
                bad_node += 1
        p = 0 if d == 10 else (2 * p + rem)

print("invariant violations:", bad_inv, "/ 4096")
print("depth-1 parity node mismatches:", bad_node, "/ 512")

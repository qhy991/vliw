"""Dir #01 D3 gather tail grid sweep on the 1208 op-graph.

Scans D3_GATHER_TAIL=0..8 x COMBINE_TAIL in {80,90,100,110,120}, COMBINE_HEAD=24,
using the KernelBuilder._rotations shortlist [0,1,2,26,30,31] to accelerate.
Records bundle count (== cycles for batch=256, n_groups=1).
"""
import sys
from perf_takehome import KernelBuilder

# Full 32-rotation search per cell (a full build is ~10s; grid ~7.5min).
# The task's suggested shortlist [0,1,2,26,30,31] misses the real winner
# (rot 29 -> 1208), so we use ground-truth all-rotations here.
SHORTLIST = None
D3_RANGE = range(0, 9)
COMBINE_TAILS = [80, 90, 100, 110, 120]


def build(d3, ctail, rots):
    kb = KernelBuilder()
    kb._rotations = rots
    kb._d3_gather_tail = d3
    kb._combine_head = 24
    kb._combine_tail = ctail
    kb.build_kernel(10, 2047, 256, 16)
    return len(kb.instrs)


def main():
    print(f"rotations={'ALL' if SHORTLIST is None else SHORTLIST}")
    print(f"{'d3':>3} | " + " ".join(f"ct{ct:>3}" for ct in COMBINE_TAILS))
    best = (10**9, None)
    grid = {}
    for d3 in D3_RANGE:
        row = []
        for ct in COMBINE_TAILS:
            c = build(d3, ct, SHORTLIST)
            grid[(d3, ct)] = c
            row.append(c)
            if c < best[0]:
                best = (c, (d3, ct))
        print(f"{d3:>3} | " + " ".join(f"{c:>5}" for c in row))
        sys.stdout.flush()
    print(f"\nbest (shortlist): {best[0]} cycles at d3={best[1][0]}, combine_tail={best[1][1]}")
    return grid, best


if __name__ == "__main__":
    main()

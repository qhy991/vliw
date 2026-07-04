"""Structural-knob grid over full 32-rotation builds (the real min-over-rot).
These knobs (step, key_idx, num_mtmp_groups) reshape the schedule, unlike the
mask which the profile shows is saturated. All correctness-safe (they only
reorder independent ops / pick scratch groups)."""
import multiprocessing as mp
import time
import perf_takehome as P

SHAPE = (10, 2**11-1, 256, 16)
K_VEC, ROUNDS = 32, 16
N_COMBINE = 3*K_VEC*ROUNDS

def seed(head=10, tail=100):
    return [(gi < head or gi >= N_COMBINE - tail) for gi in range(N_COMBINE)]

def _build(args):
    step, key_idx, groups, use_seed = args
    kb = P.KernelBuilder()
    if use_seed:
        kb._combine_mask = seed()
    kb._step = step; kb._key_idx = key_idx; kb._num_mtmp_groups = groups
    # full build (all rotations) -> real min-over-rot count
    t0 = time.time()
    kb.build_kernel(*SHAPE)
    return (step, key_idx, groups, use_seed), len(kb.instrs), time.time()-t0

if __name__ == "__main__":
    grid = []
    for step in (3, 4, 5, 6):
        for key_idx in (0, 1, 2, 3, 4):
            for groups in (3, 4):
                grid.append((step, key_idx, groups, True))
    t0 = time.time()
    with mp.Pool(8) as pool:
        res = pool.map(_build, grid)
    wall = time.time()-t0
    res.sort(key=lambda r: r[1])
    print(f"{len(grid)} full builds in {wall:.1f}s\n")
    print("cycles  step key grp seed")
    for (s,k,g,sd), c, dt in res:
        mark = "  <== " if c < 1230 else ("  = best" if c==1230 else "")
        print(f"{c:5d}   {s:3d} {k:3d} {g:3d}  {int(sd)}{mark}")
    print(f"\nBEST: {res[0][1]} at {res[0][0]}")

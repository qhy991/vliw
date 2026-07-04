"""Joint (step, head, tail) grid on FULL 32-rotation builds. The notes tested
step standalone and head/tail standalone (tuned for step=4); their interaction
is unexplored. Full build = real min-over-rotations = shippable number."""
import multiprocessing as mp
import time
import perf_takehome as P

SHAPE = (10, 2**11-1, 256, 16)
K_VEC, ROUNDS = 32, 16
N_COMBINE = 3*K_VEC*ROUNDS

def mask_ht(head, tail):
    return [(gi < head or gi >= N_COMBINE - tail) for gi in range(N_COMBINE)]

def _build(args):
    step, head, tail = args
    kb = P.KernelBuilder()
    kb._combine_mask = mask_ht(head, tail)
    kb._step = step
    kb.build_kernel(*SHAPE)
    return (step, head, tail), len(kb.instrs)

if __name__ == "__main__":
    grid = []
    for step in (3, 4, 5):
        for head in (0, 6, 10, 16, 24):
            for tail in (60, 88, 100, 120, 160):
                grid.append((step, head, tail))
    t0 = time.time()
    with mp.Pool(8) as pool:
        res = pool.map(_build, grid)
    wall = time.time()-t0
    res.sort(key=lambda r: r[1])
    print(f"{len(grid)} full builds in {wall:.1f}s (min-over-rot)\n")
    print("cyc   step head tail")
    for (s,h,t), c in res[:25]:
        mark = "  <== BEAT" if c < 1230 else ("  =1230" if c==1230 else "")
        print(f"{c}  {s:4d} {h:4d} {t:4d}{mark}")
    print(f"\nBEST {res[0][1]} at step,head,tail={res[0][0]}")

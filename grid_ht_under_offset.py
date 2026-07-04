"""Joint re-tune of (head, tail) AND the combine mask UNDER the 1225 offset
schedule. The offsets moved which combines fall in windup/drain, so the mask
optimum may have shifted. Full builds (min over 32 rot)."""
import multiprocessing as mp
import time
import perf_takehome as P

SHAPE = (10, 2 ** 11 - 1, 256, 16)
K_VEC, ROUNDS = 32, 16
N_COMBINE = 3 * K_VEC * ROUNDS
OFF = [0, 0, 1, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3,
       4, 4, 4, 4, 6, 5, 5, 6, 6, 7, 6, 6, 7, 7, 7, 7]


def mask_ht(head, tail):
    return [(gi < head or gi >= N_COMBINE - tail) for gi in range(N_COMBINE)]


def _build(args):
    head, tail = args
    kb = P.KernelBuilder()
    kb._combine_mask = mask_ht(head, tail)
    kb._pos_offset = OFF
    kb.build_kernel(*SHAPE)
    return (head, tail), len(kb.instrs)


if __name__ == "__main__":
    grid = [(h, t) for h in (0, 4, 8, 10, 12, 16, 20)
            for t in (60, 80, 88, 100, 112, 130, 160)]
    t0 = time.time()
    with mp.Pool(8) as pool:
        res = pool.map(_build, grid)
    res.sort(key=lambda r: r[1])
    print(f"{len(grid)} full builds in {time.time()-t0:.1f}s (offset=1225 champ)\n")
    print("cyc   head tail")
    for (h, t), c in res[:15]:
        mark = "  <== <1225" if c < 1225 else ("  =1225" if c == 1225 else "")
        print(f"{c}  {h:4d} {t:4d}{mark}")
    print(f"\nBEST {res[0][1]} at head,tail={res[0][0]}")

"""Search per-position emit offsets (generalizing p//step). Uses the fast
single-rot oracle on a few good rotations. Default offsets = [p//4] -> 1230."""
import multiprocessing as mp
import time
import perf_takehome as P

SHAPE = (10, 2 ** 11 - 1, 256, 16)
K_VEC, ROUNDS = 32, 16
N_COMBINE = 3 * K_VEC * ROUNDS
K = K_VEC


def seed():
    return [(gi < 10 or gi >= N_COMBINE - 100) for gi in range(N_COMBINE)]


def build_count(offsets, rot, cmask=None):
    kb = P.KernelBuilder()
    kb._combine_mask = cmask if cmask is not None else seed()
    kb._pos_offset = offsets
    kb._rotations = [rot]
    kb.build_kernel(*SHAPE)
    return len(kb.instrs)


def build_full(offsets, cmask=None):
    kb = P.KernelBuilder()
    kb._combine_mask = cmask if cmask is not None else seed()
    kb._pos_offset = offsets
    kb.build_kernel(*SHAPE)
    return len(kb.instrs)


# candidate offset generators (all length K=32, non-decreasing helps the
# diagonal but not required)
def gen_candidates():
    cands = {}
    cands["default p//4"] = [p // 4 for p in range(K)]
    for step in (3, 4, 5):
        cands[f"p//{step}"] = [p // step for p in range(K)]
    # compressed tail: last block starts earlier (denser drain)
    base = [p // 4 for p in range(K)]
    # stretch head, compress tail
    cands["compress-tail"] = [min(p // 4, 6) for p in range(K)]
    cands["stretch-head"] = [ (p//2 if p < 8 else 4 + (p-8)//4) for p in range(K)]
    # linear ramps with different slopes
    for denom in (3, 4, 5, 6):
        cands[f"ramp/{denom}"] = [round(p / denom) for p in range(K)]
    # front-loaded then plateau
    cands["plateau8"] = [min(p // 4, 8) for p in range(K)]
    return cands


def _run(job):
    name, off, rot = job
    return name, rot, build_count(off, rot)


if __name__ == "__main__":
    import sys
    rots = [31, 30, 29, 27, 25]
    cands = gen_candidates()
    print(f"testing {len(cands)} offset patterns x {len(rots)} rots "
          f"(single-rot oracle)\n")
    jobs = []
    for name, off in cands.items():
        for rot in rots:
            jobs.append((name, off, rot))

    t0 = time.time()
    with mp.Pool(8) as pool:
        res = pool.map(_run, jobs)
    wall = time.time() - t0
    # best per candidate (min over the tested rots)
    byname = {}
    for name, rot, c in res:
        if name not in byname or c < byname[name][1]:
            byname[name] = (rot, c)
    print(f"{len(jobs)} evals in {wall:.1f}s\n")
    print("pattern            best-rot  min-cyc")
    for name in cands:
        rot, c = byname[name]
        mark = "  <== <1230" if c < 1230 else ("  =1230" if c == 1230 else "")
        print(f"{name:18s}  rot={rot:2d}   {c}{mark}")
    winner = min(byname.items(), key=lambda kv: kv[1][1])
    print(f"\nBEST single-rot: {winner[0]} -> {winner[1][1]} at rot={winner[1][0]}")

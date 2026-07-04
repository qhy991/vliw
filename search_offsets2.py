"""Randomized + greedy search over per-position emit offsets. Module-level
worker for spawn compatibility. Oracle = single-rot on a small rotation set;
champions get a full build. Correctness-safe (reorders independent work)."""
import multiprocessing as mp
import random
import time
import perf_takehome as P

SHAPE = (10, 2 ** 11 - 1, 256, 16)
K_VEC, ROUNDS = 32, 16
N_COMBINE = 3 * K_VEC * ROUNDS
K = K_VEC


def seed():
    return [(gi < 10 or gi >= N_COMBINE - 100) for gi in range(N_COMBINE)]


def build_count(offsets, rot):
    kb = P.KernelBuilder()
    kb._combine_mask = seed()
    kb._pos_offset = offsets
    kb._rotations = [rot]
    kb.build_kernel(*SHAPE)
    return len(kb.instrs)


ROTS = [31, 30, 27, 25]


def eval_offsets(offsets):
    """min over a small rotation set (cheap proxy for the full min-over-32)."""
    return min(build_count(offsets, r) for r in ROTS)


def _eval_job(args):
    idx, offsets = args
    return idx, eval_offsets(offsets), offsets


def default_off():
    return [p // 4 for p in range(K)]


def neighbor(off, rng):
    """Perturb: pick a position, nudge its offset by +-1, keep >=0 and
    non-decreasing-ish (not enforced strictly)."""
    o = list(off)
    for _ in range(rng.randint(1, 3)):
        p = rng.randrange(K)
        o[p] = max(0, o[p] + rng.choice((-1, 1)))
    return o


def main():
    rng = random.Random(12345)
    base = default_off()
    t0 = time.time()
    best_c = eval_offsets(base)
    best = base
    print(f"default offsets min-over-{len(ROTS)}rots = {best_c}  "
          f"({time.time()-t0:.1f}s)")

    # Parallel random-restart hill climb: generate a batch of neighbors, eval
    # in the pool, take improving ones, repeat.
    n_rounds = 12
    batch = 32
    with mp.Pool(8) as pool:
        for rnd in range(n_rounds):
            cands = [neighbor(best, rng) for _ in range(batch)]
            # also some fully random offsets for exploration
            for _ in range(batch // 4):
                cands.append([rng.randint(0, 10) for _ in range(K)])
            jobs = [(i, c) for i, c in enumerate(cands)]
            res = pool.map(_eval_job, jobs)
            res.sort(key=lambda r: r[1])
            bi, bc, bo = res[0]
            improved = ""
            if bc < best_c:
                best_c, best = bc, bo
                improved = "  <== IMPROVED"
            print(f"[round {rnd}] batch-best={bc} incumbent={best_c}{improved}")
    print(f"\nBEST min-over-{len(ROTS)}rots = {best_c}")
    print(f"offsets = {best}")
    # full build of champion
    if best_c <= 1230:
        kb = P.KernelBuilder(); kb._combine_mask = seed(); kb._pos_offset = best
        t0 = time.time(); kb.build_kernel(*SHAPE)
        print(f"FULL 32-rot build of champion: {len(kb.instrs)} "
              f"({time.time()-t0:.1f}s)")


if __name__ == "__main__":
    main()

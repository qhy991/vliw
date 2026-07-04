"""Aggressive offset search, seeded from the 1225 champion. Uses full 32-rot
builds as the objective for accepted moves (the real shipped number), with a
cheaper multi-rot proxy for candidate screening. Parallel neighbor batches."""
import multiprocessing as mp
import random
import time
import json
import perf_takehome as P

SHAPE = (10, 2 ** 11 - 1, 256, 16)
K_VEC, ROUNDS = 32, 16
N_COMBINE = 3 * K_VEC * ROUNDS
K = K_VEC

CHAMP = [0, 0, 1, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3,
         4, 4, 4, 4, 6, 5, 5, 6, 6, 7, 6, 6, 7, 7, 7, 7]


def seed():
    return [(gi < 10 or gi >= N_COMBINE - 100) for gi in range(N_COMBINE)]


def build_count(offsets, rot):
    kb = P.KernelBuilder()
    kb._combine_mask = seed()
    kb._pos_offset = offsets
    kb._rotations = [rot] if rot is not None else None
    kb.build_kernel(*SHAPE)
    return len(kb.instrs)


# proxy rotation set (fast screen). Include the rotations that historically
# produce the min so the proxy tracks the true min-over-32 well.
PROXY_ROTS = [31, 30, 27, 25, 24]


def proxy(offsets):
    return min(build_count(offsets, r) for r in PROXY_ROTS)


def full(offsets):
    return build_count(offsets, None)


def _proxy_job(args):
    idx, off = args
    return idx, proxy(off), off


def neighbor(off, rng, strength=1):
    o = list(off)
    for _ in range(rng.randint(1, strength)):
        p = rng.randrange(K)
        o[p] = max(0, o[p] + rng.choice((-1, 1)))
    return o


def main():
    rng = random.Random(999)
    best = list(CHAMP)
    t0 = time.time()
    best_full = full(best)
    best_proxy = proxy(best)
    print(f"seed champion: full={best_full} proxy={best_proxy} ({time.time()-t0:.1f}s)")

    incumbent = best
    inc_proxy = best_proxy
    rounds = 40
    batch = 48
    with mp.Pool(8) as pool:
        for rnd in range(rounds):
            strength = 1 + (rnd % 3)  # vary perturbation size
            cands = [neighbor(incumbent, rng, strength) for _ in range(batch)]
            jobs = [(i, c) for i, c in enumerate(cands)]
            res = pool.map(_proxy_job, jobs)
            res.sort(key=lambda r: r[1])
            bi, bp, bo = res[0]
            note = ""
            # accept if proxy improves or equal (random walk on plateau)
            if bp < inc_proxy or (bp == inc_proxy and rng.random() < 0.5):
                incumbent, inc_proxy = bo, bp
            # check the very best candidate against full build if promising
            if bp <= best_proxy:
                f = full(bo)
                if f < best_full:
                    best_full, best, best_proxy = f, bo, bp
                    note = f"  <== NEW BEST full={f}"
            print(f"[r{rnd:2d} s{strength}] batch-proxy={bp} inc_proxy={inc_proxy} "
                  f"best_full={best_full}{note}")
    print(f"\nBEST full={best_full}")
    print(f"offsets={best}")
    with open("best_offsets.json", "w") as fh:
        json.dump({"full": best_full, "offsets": best}, fh)


if __name__ == "__main__":
    main()

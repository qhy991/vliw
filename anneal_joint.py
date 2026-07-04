"""Joint simulated annealing over (per-position offsets + combine mask) using
the rot=31 single-rotation oracle (guaranteed bound: rot=31 is the argmin, so
count(.,rot=31) < X implies shipped < X). Seeded from a champion JSON if present.

Neighbor = with prob p_off perturb 1-2 offset positions, else flip 1-3 mask
bits (biased to the tail region where headroom lives). Metropolis acceptance,
geometric cooling. Periodically snapshots the best to champ_joint.json and
validates it with a full 32-rotation build.
"""
import json
import math
import os
import random
import time
import perf_takehome as P

SHAPE = (10, 2 ** 11 - 1, 256, 16)
K_VEC, ROUNDS = 32, 16
N_COMBINE = 3 * K_VEC * ROUNDS
K = K_VEC
DEFAULT_OFF = [0, 0, 1, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3,
               4, 4, 4, 4, 6, 5, 5, 6, 6, 7, 6, 6, 7, 7, 7, 7]


def seed_mask():
    return [(gi < 10 or gi >= N_COMBINE - 100) for gi in range(N_COMBINE)]


def ev(mask, off, rot=31):
    kb = P.KernelBuilder()
    kb._combine_mask = mask
    kb._pos_offset = off
    kb._rotations = [rot]
    kb.build_kernel(*SHAPE)
    return len(kb.instrs)


def full(mask, off):
    kb = P.KernelBuilder()
    kb._combine_mask = mask
    kb._pos_offset = off
    kb.build_kernel(*SHAPE)
    return len(kb.instrs)


def load_seed():
    for fn in ("champ_mask_offset.json", "champ_joint.json"):
        if os.path.exists(fn):
            with open(fn) as f:
                d = json.load(f)
            mask = [bool(b) for b in d["mask"]]
            off = list(d["offsets"])
            return mask, off, fn
    return seed_mask(), list(DEFAULT_OFF), "seed(10,100)+default-off"


def neighbor(mask, off, rng):
    mask = list(mask)
    off = list(off)
    if rng.random() < 0.4:
        # perturb offsets
        for _ in range(rng.randint(1, 2)):
            p = rng.randrange(K)
            off[p] = max(0, off[p] + rng.choice((-1, 1)))
    else:
        # flip mask bits, biased to tail (last 300 combine instances) where the
        # sweep found headroom
        for _ in range(rng.randint(1, 3)):
            if rng.random() < 0.7:
                i = rng.randrange(N_COMBINE - 340, N_COMBINE)
            else:
                i = rng.randrange(N_COMBINE)
            mask[i] = not mask[i]
    return mask, off


def main():
    rng = random.Random(2027)
    mask, off, src = load_seed()
    cur = ev(mask, off)
    best = cur
    best_mask, best_off = list(mask), list(off)
    print(f"seed from {src}: rot31={cur}")

    T = 3.0
    cooling = 0.9995
    iters = 4000
    t0 = time.time()
    accepts = 0
    for it in range(iters):
        nm, no = neighbor(mask, off, rng)
        c = ev(nm, no)
        d = c - cur
        if d <= 0 or rng.random() < math.exp(-d / max(T, 1e-6)):
            mask, off, cur = nm, no, c
            accepts += 1
            if c < best:
                best, best_mask, best_off = c, list(nm), list(no)
                print(f"[it {it} T={T:.2f}] NEW BEST rot31={c} "
                      f"({time.time()-t0:.0f}s, acc={accepts}/{it+1})")
                with open("champ_joint.json", "w") as f:
                    json.dump({"rot31": best,
                               "mask": [int(b) for b in best_mask],
                               "offsets": best_off}, f)
        T *= cooling
        if it % 500 == 499:
            print(f"  it={it} T={T:.3f} cur={cur} best={best} "
                  f"acc_rate={accepts/(it+1):.2f} ({time.time()-t0:.0f}s)")
    # validate best with full build
    f = full(best_mask, best_off)
    print(f"\nBEST rot31={best}  FULL 32-rot={f}")
    with open("champ_joint.json", "w") as fh:
        json.dump({"rot31": best, "full": f,
                   "mask": [int(b) for b in best_mask],
                   "offsets": best_off}, fh)
    print("saved champ_joint.json")


if __name__ == "__main__":
    main()

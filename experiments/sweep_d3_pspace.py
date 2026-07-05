"""D3_GATHER_TAIL × (offset + combine mask) joint search on the p-space graph.

For each D3 tail count, re-anneal mask+offset starting from champ_pspace.json
(the 1185 champion). Rank by oracle rot=27; confirm top cells with full 32-rot.
"""
import json
import math
import os
import random
import sys
import time

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
os.environ["PSPACE"] = "1"
import perf_takehome as P  # noqa: E402

SHAPE = (10, 2047, 256, 16)
K_VEC, ROUNDS = 32, 16
N_COMBINE = 3 * K_VEC * ROUNDS
ORACLE_ROT = 27
CHAMP_PATH = os.path.join(os.path.dirname(__file__), "champ_pspace.json")
BASELINE = 1185


def load_champ():
    with open(CHAMP_PATH) as f:
        d = json.load(f)
    mask = [bool(b) for b in d["mask"]]
    off = list(d["offsets"])
    return mask, off


def build(d3, mask, off, rots=None):
    kb = P.KernelBuilder()
    kb._d3_gather_tail = d3
    kb._combine_mask = list(mask)
    kb._pos_offset = list(off)
    if rots is not None:
        kb._rotations = rots
    kb.build_kernel(*SHAPE)
    return len(kb.instrs)


def neighbor(mask, off, rng):
    mask = list(mask)
    off = list(off)
    if rng.random() < 0.4:
        for _ in range(rng.randint(1, 2)):
            p = rng.randrange(K_VEC)
            off[p] = max(0, off[p] + rng.choice((-1, 1)))
    else:
        for _ in range(rng.randint(1, 3)):
            if rng.random() < 0.7:
                i = rng.randrange(N_COMBINE - 340, N_COMBINE)
            else:
                i = rng.randrange(N_COMBINE)
            mask[i] = not mask[i]
    return mask, off


def anneal_d3(d3, seed_mask, seed_off, iters=2000, seed=2027):
    rng = random.Random(seed + d3 * 1000)
    mask, off = list(seed_mask), list(seed_off)
    ev = lambda m, o: build(d3, m, o, [ORACLE_ROT])
    cur = ev(mask, off)
    best = cur
    best_mask, best_off = list(mask), list(off)
    T = 2.5
    cooling = 0.9995
    for it in range(iters):
        nm, no = neighbor(mask, off, rng)
        c = ev(nm, no)
        d = c - cur
        if d <= 0 or rng.random() < math.exp(-d / max(T, 1e-6)):
            mask, off, cur = nm, no, c
            if c < best:
                best, best_mask, best_off = c, list(nm), list(no)
        T *= cooling
    full = build(d3, best_mask, best_off, None)
    return best, full, best_mask, best_off


def main():
    seed_mask, seed_off = load_champ()
    print(f"baseline champ: rot{ORACLE_ROT}={build(0, seed_mask, seed_off, [ORACLE_ROT])} "
          f"full={build(0, seed_mask, seed_off, None)}", flush=True)

    results = []
    t0 = time.time()
    for d3 in range(9):
        rot_best, full, mask, off = anneal_d3(d3, seed_mask, seed_off, iters=2500)
        mark = " ***" if full < BASELINE else (" ==" if full == BASELINE else "")
        print(f"d3={d3}: rot{ORACLE_ROT}={rot_best} full32={full}{mark}  "
              f"[{time.time()-t0:.0f}s]", flush=True)
        results.append((full, rot_best, d3, mask, off))

    results.sort(key=lambda r: r[0])
    print("\n=== ranked (full 32-rot) ===")
    for full, rot, d3, _, _ in results:
        print(f"  d3={d3} rot{ORACLE_ROT}={rot} full={full}")

    best_full, best_rot, best_d3, best_mask, best_off = results[0]
    out = {
        "d3_gather_tail": best_d3,
        "rot_oracle": best_rot,
        "full32": best_full,
        "mask": [int(b) for b in best_mask],
        "offsets": best_off,
    }
    out_path = os.path.join(os.path.dirname(__file__), "champ_d3_pspace.json")
    with open(out_path, "w") as f:
        json.dump(out, f)
    print(f"\nBEST d3={best_d3} full32={best_full} (baseline {BASELINE})")
    print(f"saved {out_path}")
    return out


if __name__ == "__main__":
    main()

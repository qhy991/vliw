"""Focused anneal on p-space d3=0 (mux path). Saves champ_d3_pspace.json."""
import json
import math
import os
import random
import sys
import time

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
os.environ["PSPACE"] = "1"
import perf_takehome as P

SHAPE = (10, 2047, 256, 16)
N_COMBINE = 3 * 32 * 16
ORACLE_ROT = 27
D3 = 0
CHAMP = os.path.join(os.path.dirname(__file__), "champ_pspace.json")
OUT = os.path.join(os.path.dirname(__file__), "champ_d3_pspace.json")


def load():
    with open(CHAMP) as f:
        d = json.load(f)
    return [bool(b) for b in d["mask"]], list(d["offsets"])


def build(mask, off, rots=None):
    kb = P.KernelBuilder()
    kb._d3_gather_tail = D3
    kb._combine_mask = list(mask)
    kb._pos_offset = list(off)
    if rots is not None:
        kb._rotations = rots
    kb.build_kernel(*SHAPE)
    return len(kb.instrs)


def neighbor(mask, off, rng):
    mask, off = list(mask), list(off)
    if rng.random() < 0.4:
        for _ in range(rng.randint(1, 2)):
            p = rng.randrange(32)
            off[p] = max(0, off[p] + rng.choice((-1, 1)))
    else:
        for _ in range(rng.randint(1, 3)):
            i = rng.randrange(N_COMBINE - 340, N_COMBINE) if rng.random() < 0.7 else rng.randrange(N_COMBINE)
            mask[i] = not mask[i]
    return mask, off


def main():
    rng = random.Random(42)
    mask, off = load()
    ev = lambda m, o: build(m, o, [ORACLE_ROT])
    cur = ev(mask, off)
    best, best_m, best_o = cur, list(mask), list(off)
    print(f"seed rot{ORACLE_ROT}={cur} full={build(mask, off, None)}", flush=True)
    T, cool = 2.5, 0.9996
    t0 = time.time()
    for it in range(8000):
        nm, no = neighbor(mask, off, rng)
        c = ev(nm, no)
        d = c - cur
        if d <= 0 or rng.random() < math.exp(-d / max(T, 1e-6)):
            mask, off, cur = nm, no, c
            if c < best:
                best, best_m, best_o = c, list(nm), list(no)
                print(f"[{it}] NEW rot{ORACLE_ROT}={c} ({time.time()-t0:.0f}s)", flush=True)
        T *= cool
        if it % 1000 == 999:
            print(f"  it={it} best_rot={best} best_full={build(best_m, best_o, None)}", flush=True)
    full = build(best_m, best_o, None)
    out = {"d3_gather_tail": D3, "oracle_rot": ORACLE_ROT,
           "rot_oracle_cycles": best, "full32": full,
           "mask": [int(b) for b in best_m], "offsets": best_o}
    with open(OUT, "w") as f:
        json.dump(out, f)
    print(f"\nDONE best_rot={best} full32={full} -> {OUT}", flush=True)


if __name__ == "__main__":
    main()

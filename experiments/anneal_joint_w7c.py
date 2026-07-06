"""W7-C joint SA over (pos_offset + combine mask) at 1093.

Both the shipped combine mask and pos_offset are single-axis local optima
(single-flip combine scan = 0 improvements; every random offset step regresses).
This searches the JOINT space in case a coupled move escapes.

Oracle = min over rotations {25,27,29} (verified to track full-32 under offset
perturbation; plain rot29 misreads offset moves by up to +10). Every new oracle
best is confirmed with a full-32 build. Correctness is untouched: pos_offset only
reschedules independent vector work; the combine mask only picks the engine of an
arithmetically identical XOR.

Win: full-32 < 1093 -> champ_joint_w7c.json.
"""
import json, math, os, random, time, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["PSPACE"] = "1"
import perf_takehome as P

SHAPE = (10, 2 ** 11 - 1, 256, 16)
K, ROUNDS = 32, 16
N = 3 * K * ROUNDS
ORACLE_ROTS = (25, 27, 29)
CHAMP = set(P._COMBINE_VALU_PSPACE_32x16)
SEED_MASK = [i in CHAMP for i in range(N)]
SEED_OFF = list(P._POS_OFFSET_PSPACE_32x16)


def ev(mask, off, rots=ORACLE_ROTS):
    best = 10 ** 9
    for rot in rots:
        kb = P.KernelBuilder()
        kb._combine_mask = list(mask)
        kb._pos_offset = list(off)
        kb._rotations = [rot]
        kb.build_kernel(*SHAPE)
        best = min(best, len(kb.instrs))
    return best


def full(mask, off):
    kb = P.KernelBuilder()
    kb._combine_mask = list(mask)
    kb._pos_offset = list(off)
    kb.build_kernel(*SHAPE)
    return len(kb.instrs)


def neighbor(mask, off, rng):
    mask = list(mask)
    off = list(off)
    r = rng.random()
    if r < 0.45:                       # offset move
        for _ in range(rng.randint(1, 2)):
            p = rng.randrange(K)
            off[p] = max(0, off[p] + rng.choice((-1, 1)))
    else:                              # combine bit move
        for _ in range(rng.randint(1, 3)):
            i = rng.randrange(N)
            mask[i] = not mask[i]
    return mask, off


def main():
    seed = int(os.environ.get("SEED", "4001"))
    iters = int(os.environ.get("ITERS", "6000"))
    T0 = float(os.environ.get("T0", "3.0"))
    cooling = float(os.environ.get("COOL", "0.9993"))
    rng = random.Random(seed)
    mask, off = list(SEED_MASK), list(SEED_OFF)
    seed_full = full(mask, off)
    cur = ev(mask, off)
    best = cur
    best_mask, best_off = list(mask), list(off)
    print(f"seed: oracle={cur}  FULL-32={seed_full}", flush=True)
    T = T0
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
                fc = full(nm, no)
                tag = "WIN" if fc < seed_full else "flat/regress-full"
                print(f"[it {it} T={T:.2f}] oracle={c} FULL-32={fc} [{tag}] "
                      f"({time.time()-t0:.0f}s)", flush=True)
                best, best_mask, best_off = c, list(nm), list(no)
                if fc < seed_full:
                    with open("champ_joint_w7c.json", "w") as f:
                        json.dump({"oracle": c, "full": fc,
                                   "mask": [int(b) for b in nm], "offsets": no}, f)
        T *= cooling
        if it % 400 == 399:
            print(f"  it={it} T={T:.3f} cur={cur} best={best} "
                  f"acc={accepts/(it+1):.2f} ({time.time()-t0:.0f}s)", flush=True)
    fc = full(best_mask, best_off)
    print(f"\nBEST oracle={best} FULL-32={fc} (seed full={seed_full})", flush=True)
    if fc < seed_full:
        with open("champ_joint_w7c.json", "w") as f:
            json.dump({"oracle": best, "full": fc,
                       "mask": [int(b) for b in best_mask], "offsets": best_off}, f)
        print("WIN saved champ_joint_w7c.json", flush=True)
    else:
        print("no full-32 improvement", flush=True)


if __name__ == "__main__":
    main()

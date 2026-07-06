"""W7-C: SA over the p-space combine engine mask (1536 instances) at 1093.

Seed = shipped _COMBINE_VALU_PSPACE_32x16 (539 valu). Objective = rot29 single
rotation (0.3s, verified to equal full-32 at the seed and track it bit-exact
under perturbation, see /tmp/track.py). Every new rot29 best is confirmed with a
full-32 build before it is trusted. Correctness is untouched: the mask only picks
which engine (valu 1-slot vs alu 8-slot) emits an arithmetically identical XOR.

Win: full-32 < 1093. Writes champ to champ_combine_w7c.json.
"""
import json, math, os, random, time, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["PSPACE"] = "1"
import perf_takehome as P

SHAPE = (10, 2 ** 11 - 1, 256, 16)
K, ROUNDS = 32, 16
N = 3 * K * ROUNDS         # 1536 combine instances
ORACLE = 29


def ev(mask, rot=ORACLE):
    kb = P.KernelBuilder()
    kb._combine_mask = list(mask)
    kb._rotations = [rot]
    kb.build_kernel(*SHAPE)
    return len(kb.instrs)


def full(mask):
    kb = P.KernelBuilder()
    kb._combine_mask = list(mask)
    kb.build_kernel(*SHAPE)
    return len(kb.instrs)


def seed_mask():
    champ = set(P._COMBINE_VALU_PSPACE_32x16)
    return [i in champ for i in range(N)]


def load_seed():
    if os.path.exists("champ_combine_w7c.json"):
        with open("champ_combine_w7c.json") as f:
            d = json.load(f)
        return [bool(b) for b in d["mask"]], "champ_combine_w7c.json"
    return seed_mask(), "shipped _COMBINE_VALU_PSPACE_32x16"


def neighbor(mask, rng):
    m = list(mask)
    for _ in range(rng.randint(1, 3)):
        i = rng.randrange(N)
        m[i] = not m[i]
    return m


def main():
    seed = int(os.environ.get("SEED", "2029"))
    iters = int(os.environ.get("ITERS", "8000"))
    T0 = float(os.environ.get("T0", "2.5"))
    rng = random.Random(seed)
    mask, src = load_seed()
    cur = ev(mask)
    best = cur
    best_mask = list(mask)
    seed_full = full(mask)
    print(f"seed from {src}: rot{ORACLE}={cur}  FULL-32={seed_full}  "
          f"(valu={sum(mask)}/{N})", flush=True)

    T = T0
    cooling = float(os.environ.get("COOL", "0.9994"))
    t0 = time.time()
    accepts = 0
    for it in range(iters):
        nm = neighbor(mask, rng)
        c = ev(nm)
        d = c - cur
        if d <= 0 or rng.random() < math.exp(-d / max(T, 1e-6)):
            mask, cur = nm, c
            accepts += 1
            if c < best:
                fc = full(nm)
                tag = "WIN" if fc < seed_full else "flat/regress-full"
                print(f"[it {it} T={T:.2f}] rot{ORACLE}={c} FULL-32={fc} "
                      f"valu={sum(nm)} [{tag}] ({time.time()-t0:.0f}s)", flush=True)
                if fc < seed_full or (c < best):
                    best, best_mask = c, list(nm)
                if fc < seed_full:
                    with open("champ_combine_w7c.json", "w") as f:
                        json.dump({"rot": c, "full": fc,
                                   "mask": [int(b) for b in nm]}, f)
        T *= cooling
        if it % 500 == 499:
            print(f"  it={it} T={T:.3f} cur={cur} best_rot={best} "
                  f"acc={accepts/(it+1):.2f} ({time.time()-t0:.0f}s)", flush=True)
    fc = full(best_mask)
    print(f"\nBEST rot{ORACLE}={best}  FULL-32={fc}  (seed full={seed_full})",
          flush=True)
    if fc < seed_full:
        with open("champ_combine_w7c.json", "w") as f:
            json.dump({"rot": best, "full": fc,
                       "mask": [int(b) for b in best_mask]}, f)
        print("WIN saved champ_combine_w7c.json", flush=True)
    else:
        print("no full-32 improvement", flush=True)


if __name__ == "__main__":
    main()

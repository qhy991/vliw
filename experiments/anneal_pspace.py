"""Joint simulated annealing over (per-position offsets + combine mask) for the
p-space (#12) graph. p-space deletes ~248 valu ops, so the old shipped offset
(_POS_OFFSET_32x16, tuned on the 1208 graph) and combine mask are stale. Re-search
both. Oracle = rot=27 single-rotation (argmin under p-space); best is periodically
confirmed with a full 32-rotation build.
"""
import json, math, os, random, time, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["PSPACE"] = "1"
import perf_takehome as P

SHAPE = (10, 2 ** 11 - 1, 256, 16)
K_VEC, ROUNDS = 32, 16
N_COMBINE = 3 * K_VEC * ROUNDS
K = K_VEC
ORACLE_ROT = 27

# Seed offset = current shipped searched offset (best starting point we have).
SEED_OFF = list(P._POS_OFFSET_32x16)


def seed_mask():
    # head/tail heuristic tuned for p-space balance (~40/140 from sweep).
    head, tail = 40, 140
    return [(gi < head or gi >= N_COMBINE - tail) for gi in range(N_COMBINE)]


def ev(mask, off, rot=ORACLE_ROT):
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
    if os.path.exists("champ_pspace.json"):
        with open("champ_pspace.json") as f:
            d = json.load(f)
        return [bool(b) for b in d["mask"]], list(d["offsets"]), "champ_pspace.json"
    return seed_mask(), list(SEED_OFF), "seed(40,140)+shipped-off"


def neighbor(mask, off, rng):
    mask = list(mask); off = list(off)
    if rng.random() < 0.4:
        for _ in range(rng.randint(1, 2)):
            p = rng.randrange(K)
            off[p] = max(0, off[p] + rng.choice((-1, 1)))
    else:
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
    best = cur; best_mask, best_off = list(mask), list(off)
    print(f"seed from {src}: rot{ORACLE_ROT}={cur}", flush=True)
    print(f"seed FULL 32-rot = {full(mask, off)}", flush=True)

    T = 3.0; cooling = 0.9994; iters = 5000
    t0 = time.time(); accepts = 0
    for it in range(iters):
        nm, no = neighbor(mask, off, rng)
        c = ev(nm, no)
        d = c - cur
        if d <= 0 or rng.random() < math.exp(-d / max(T, 1e-6)):
            mask, off, cur = nm, no, c; accepts += 1
            if c < best:
                best, best_mask, best_off = c, list(nm), list(no)
                print(f"[it {it} T={T:.2f}] NEW BEST rot{ORACLE_ROT}={c} "
                      f"({time.time()-t0:.0f}s)", flush=True)
                with open("champ_pspace.json", "w") as f:
                    json.dump({"rot": best, "mask": [int(b) for b in best_mask],
                               "offsets": best_off}, f)
        T *= cooling
        if it % 400 == 399:
            fc = full(best_mask, best_off)
            print(f"  it={it} T={T:.3f} cur={cur} best_rot={best} best_FULL={fc} "
                  f"acc={accepts/(it+1):.2f} ({time.time()-t0:.0f}s)", flush=True)
    f = full(best_mask, best_off)
    print(f"\nBEST rot{ORACLE_ROT}={best}  FULL 32-rot={f}", flush=True)
    with open("champ_pspace.json", "w") as fh:
        json.dump({"rot": best, "full": f, "mask": [int(b) for b in best_mask],
                   "offsets": best_off}, fh)
    print("saved champ_pspace.json")


if __name__ == "__main__":
    main()

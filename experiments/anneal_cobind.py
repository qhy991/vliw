"""Co-bind anneal for p-space graph @1184.

After #12 p-space, valu is the sole binding floor (~1107) while alu has ~144
cycles of slack (~963). The shipped champ mask (347 valu combines) was tuned when
alu was binding — reverse rebalance (valu→alu) lowers the co-bind floor.

Neighbor bias: flip combine mask True→False (valu→alu) more often than the
reverse. Joint search over (mask, offset) with periodic full 32-rotation confirm.

Usage:
  cd vliw && python experiments/anneal_cobind.py
"""
import json, math, os, random, time, sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["PSPACE"] = "1"
import perf_takehome as P

SHAPE = (10, 2 ** 11 - 1, 256, 16)
K_VEC, ROUNDS = 32, 16
N_COMBINE = 3 * K_VEC * ROUNDS
K = K_VEC
ORACLE_ROT = 27
OUT = os.path.join(os.path.dirname(__file__), "..", "champ_cobind.json")


def shipped_mask():
    m = [False] * N_COMBINE
    for gi in P._COMBINE_VALU_PSPACE_32x16:
        m[gi] = True
    return m


def engine_floors(kb):
    eng = Counter()
    for b in kb.instrs:
        if isinstance(b, dict):
            for e, slots in b.items():
                eng[e] += len(slots)
    return {e: eng[e] / {"valu": 6, "alu": 12, "load": 2, "flow": 1, "store": 2}[e]
            for e in ("valu", "alu", "load")}


def build(mask, off, rot=None, full=False):
    kb = P.KernelBuilder()
    kb._combine_mask = mask
    kb._pos_offset = off
    if rot is not None:
        kb._rotations = [rot]
    elif not full:
        kb._rotations = [ORACLE_ROT]
    kb.build_kernel(*SHAPE)
    return kb, len(kb.instrs)


def ev(mask, off):
    _, c = build(mask, off)
    return c


def full(mask, off):
    _, c = build(mask, off, full=True)
    return c


def load_seed():
    for path in (OUT, "champ_cobind.json", "champ_pspace.json"):
        if os.path.exists(path):
            with open(path) as f:
                d = json.load(f)
            mask = [bool(b) for b in d["mask"]]
            off = list(d["offsets"])
            return mask, off, path
    return shipped_mask(), list(P._POS_OFFSET_PSPACE_32x16), "shipped"


def neighbor(mask, off, rng):
    mask = list(mask)
    off = list(off)
    r = rng.random()
    if r < 0.35:
        for _ in range(rng.randint(1, 2)):
            p = rng.randrange(K)
            off[p] = max(0, off[p] + rng.choice((-1, 1)))
    elif r < 0.75:
        # bias: move combines valu→alu (True→False)
        n_flip = rng.randint(1, 4)
        for _ in range(n_flip):
            if rng.random() < 0.72:
                cands = [i for i, b in enumerate(mask) if b and 40 <= i < N_COMBINE - 140]
                if not cands:
                    cands = [i for i, b in enumerate(mask) if b]
                if cands:
                    mask[rng.choice(cands)] = False
            else:
                cands = [i for i, b in enumerate(mask) if not b]
                if cands:
                    mask[rng.choice(cands)] = True
    else:
        for _ in range(rng.randint(1, 3)):
            i = rng.randrange(N_COMBINE)
            mask[i] = not mask[i]
    return mask, off


def main():
    rng = random.Random(2028)
    mask, off, src = load_seed()
    cur = ev(mask, off)
    best = cur
    best_mask, best_off = list(mask), list(off)
    n_valu = sum(mask)
    print(f"seed from {src}: rot{ORACLE_ROT}={cur} valu_combines={n_valu}", flush=True)
    print(f"seed FULL 32-rot = {full(mask, off)}", flush=True)

    T = 2.5
    cooling = 0.9995
    iters = 8000
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
                kb, _ = build(best_mask, best_off)
                fl = engine_floors(kb)
                print(
                    f"[it {it} T={T:.2f}] NEW BEST rot{ORACLE_ROT}={c} "
                    f"valu={sum(nm)} floors v={fl['valu']:.1f} a={fl['alu']:.1f} "
                    f"({time.time()-t0:.0f}s)",
                    flush=True,
                )
                with open(OUT, "w") as f:
                    json.dump(
                        {
                            "rot": best,
                            "mask": [int(b) for b in best_mask],
                            "offsets": best_off,
                            "valu_combines": sum(best_mask),
                        },
                        f,
                    )
        T *= cooling
        if it % 500 == 499:
            fc = full(best_mask, best_off)
            print(
                f"  it={it} T={T:.3f} cur={cur} best_rot={best} best_FULL={fc} "
                f"valu={sum(best_mask)} acc={accepts/(it+1):.2f} ({time.time()-t0:.0f}s)",
                flush=True,
            )
    fc = full(best_mask, best_off)
    print(f"\nBEST rot{ORACLE_ROT}={best}  FULL 32-rot={fc}  valu={sum(best_mask)}", flush=True)
    with open(OUT, "w") as fh:
        json.dump(
            {
                "rot": best,
                "full": fc,
                "mask": [int(b) for b in best_mask],
                "offsets": best_off,
                "valu_combines": sum(best_mask),
            },
            fh,
        )
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()

"""Joint (combine, extract, offset) anneal for the d2/d3 valu->alu lever.

Post-#12/#14 @1179: valu is sole binding (~1099), alu slack ~105. There are 320
d2/d3 traverse *extract* ops/rotation currently all on valu. Migrating a subset
to alu (v_alu_ex mask False) lowers the valu floor; break-even ~125 migrations
(valu 1099->~1078, alu 995->~1078). Blanket migration of all 320 over-shoots
(alu 1208). So search a selective mask jointly with the combine mask + offset.

Seeds from champ_cobind.json (combine+offset). extract_mask starts all-True
(== shipped 1179). rot27 oracle proxy; periodic full-32 confirm.

Usage: cd vliw && python experiments/anneal_extract.py
"""
import json, math, os, random, time, sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["PSPACE"] = "1"
import perf_takehome as P

SHAPE = (10, 2 ** 11 - 1, 256, 16)
K = 32
ROUNDS = 16
N_COMBINE = 3 * K * ROUNDS
ORACLE_ROT = 27
OUT = os.path.join(os.path.dirname(__file__), "..", "champ_extract.json")
COBIND = os.path.join(os.path.dirname(__file__), "..", "champ_cobind.json")


def n_extract():
    kb = P.KernelBuilder()
    kb._rotations = [ORACLE_ROT]
    kb.build_kernel(*SHAPE)
    return kb._extract_no


def shipped_combine():
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
    return {e: eng[e] / {"valu": 6, "alu": 12, "load": 2, "flow": 1}[e]
            for e in ("valu", "alu", "load")}


def build(cmask, emask, off, rot=ORACLE_ROT, full=False):
    kb = P.KernelBuilder()
    kb._combine_mask = cmask
    kb._extract_mask = emask
    kb._pos_offset = off
    if not full:
        kb._rotations = [rot]
    kb.build_kernel(*SHAPE)
    return kb, len(kb.instrs)


def ev(cmask, emask, off):
    return build(cmask, emask, off)[1]


def full(cmask, emask, off):
    return build(cmask, emask, off, full=True)[1]


def load_seed(NE):
    cmask = shipped_combine()
    off = list(P._POS_OFFSET_PSPACE_32x16)
    if os.path.exists(COBIND):
        with open(COBIND) as f:
            d = json.load(f)
        cmask = [bool(b) for b in d["mask"]]
        off = list(d["offsets"])
    emask = [True] * NE
    if os.path.exists(OUT):
        with open(OUT) as f:
            d = json.load(f)
        cmask = [bool(b) for b in d["cmask"]]
        emask = [bool(b) for b in d["emask"]]
        off = list(d["offsets"])
    return cmask, emask, off


def neighbor(cmask, emask, off, rng):
    cmask, emask, off = list(cmask), list(emask), list(off)
    r = rng.random()
    if r < 0.25:
        for _ in range(rng.randint(1, 2)):
            p = rng.randrange(K)
            off[p] = max(0, off[p] + rng.choice((-1, 1)))
    elif r < 0.70:
        # extract: bias valu->alu (True->False) to shed valu floor
        for _ in range(rng.randint(1, 5)):
            if rng.random() < 0.65:
                cands = [i for i, b in enumerate(emask) if b]
            else:
                cands = [i for i, b in enumerate(emask) if not b]
            if cands:
                emask[rng.choice(cands)] ^= True
    else:
        # combine rebalance (either direction)
        for _ in range(rng.randint(1, 3)):
            i = rng.randrange(N_COMBINE)
            cmask[i] = not cmask[i]
    return cmask, emask, off


def save(path, cmask, emask, off, rot, fc=None):
    with open(path, "w") as f:
        json.dump({"rot": rot, "full": fc,
                   "cmask": [int(b) for b in cmask],
                   "emask": [int(b) for b in emask],
                   "offsets": off,
                   "valu_extracts": sum(emask),
                   "valu_combines": sum(cmask)}, f)


def main():
    NE = n_extract()
    rng = random.Random(4041)
    cmask, emask, off = load_seed(NE)
    cur = ev(cmask, emask, off)
    best = cur
    bc, be, bo = list(cmask), list(emask), list(off)
    seed_full = full(cmask, emask, off)
    print(f"N_extract/rot={NE}  seed rot{ORACLE_ROT}={cur} FULL32={seed_full} "
          f"valu_ex={sum(emask)} valu_comb={sum(cmask)}", flush=True)

    T = 2.5
    cooling = 0.9994
    iters = int(os.environ.get("ITERS", "6000"))
    t0 = time.time()
    accepts = 0
    for it in range(iters):
        nc, ne, no = neighbor(cmask, emask, off, rng)
        c = ev(nc, ne, no)
        d = c - cur
        if d <= 0 or rng.random() < math.exp(-d / max(T, 1e-6)):
            cmask, emask, off, cur = nc, ne, no, c
            accepts += 1
            if c < best:
                best, bc, be, bo = c, list(nc), list(ne), list(no)
                kb, _ = build(bc, be, bo)
                fl = engine_floors(kb)
                print(f"[it {it} T={T:.2f}] BEST rot={c} valu_ex={sum(ne)} "
                      f"v={fl['valu']:.1f} a={fl['alu']:.1f} l={fl['load']:.1f} "
                      f"({time.time()-t0:.0f}s)", flush=True)
                save(OUT, bc, be, bo, best)
        T *= cooling
        if it % 400 == 399:
            fc = full(bc, be, bo)
            print(f"  it={it} T={T:.3f} cur={cur} best_rot={best} FULL32={fc} "
                  f"valu_ex={sum(be)} acc={accepts/(it+1):.2f} "
                  f"({time.time()-t0:.0f}s)", flush=True)
            if fc < seed_full:
                save(OUT, bc, be, bo, best, fc)

    fc = full(bc, be, bo)
    print(f"\nBEST rot={best} FULL32={fc} valu_ex={sum(be)} valu_comb={sum(bc)}",
          flush=True)
    save(OUT, bc, be, bo, best, fc)
    print(f"saved {OUT} (seed_full={seed_full})")


if __name__ == "__main__":
    main()

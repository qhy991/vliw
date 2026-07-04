"""Offline mask search for perf_takehome.py (NOT in submission path).

Oracle: count(mask, rot=31). Since the shipped build takes min over all 32
rotations and rot=31 is the current argmin (=1230), any mask with
count(mask, rot=31) < 1230 is a GUARANTEED shipped improvement:
    full_build(mask) = min_rot count(mask, rot) <= count(mask, rot=31).

Phases: single-bit sweep (Day-1 kill test) -> greedy coordinate descent ->
simulated annealing. Champions re-checked with full 32-rot build.
"""
import argparse
import json
import multiprocessing as mp
import os
import time

import perf_takehome as P

SHAPE = (10, 2 ** 11 - 1, 256, 16)
K_VEC, ROUNDS = 32, 16
N_COMBINE = 3 * K_VEC * ROUNDS   # 1536
N_XOR = K_VEC * ROUNDS           # 512
ORACLE_ROT = 31                  # current argmin rotation

BEST_FILE = "best_mask.json"


def seed_mask(head=10, tail=100):
    return [(gi < head or gi >= N_COMBINE - tail) for gi in range(N_COMBINE)]


def eval_mask(combine_mask, rot=ORACLE_ROT, xor_mask=None,
              step=4, key_idx=0, groups=3):
    kb = P.KernelBuilder()
    kb._combine_mask = list(combine_mask) if combine_mask is not None else None
    kb._xor_mask = list(xor_mask) if xor_mask is not None else None
    kb._step = step
    kb._key_idx = key_idx
    kb._num_mtmp_groups = groups
    kb._rotations = [rot] if rot is not None else None
    kb.build_kernel(*SHAPE)
    return len(kb.instrs)


def eval_full(combine_mask, xor_mask=None, step=4, key_idx=0, groups=3):
    return eval_mask(combine_mask, rot=None, xor_mask=xor_mask,
                     step=step, key_idx=key_idx, groups=groups)


# ------------------------------------------------------------------ #
# worker: flip one combine bit from the shared base and eval rot=31
# ------------------------------------------------------------------ #
_BASE = None
_XOR = None
_STEP = 4
_KEY = 0
_GRP = 3
_ROT = ORACLE_ROT


def _init(base, xor, step, key_idx, groups, rot=ORACLE_ROT):
    global _BASE, _XOR, _STEP, _KEY, _GRP, _ROT
    _BASE, _XOR, _STEP, _KEY, _GRP, _ROT = base, xor, step, key_idx, groups, rot


def _flip_eval(i):
    m = list(_BASE)
    m[i] = not m[i]
    c = eval_mask(m, rot=_ROT, xor_mask=_XOR, step=_STEP, key_idx=_KEY, groups=_GRP)
    return i, c


def _flip_eval_xor(i):
    """Flip one XOR-mask bit instead of a combine bit."""
    x = list(_XOR) if _XOR is not None else _emit_depths(_ROT)
    x[i] = not x[i]
    c = eval_mask(_BASE, rot=_ROT, xor_mask=x, step=_STEP, key_idx=_KEY, groups=_GRP)
    return i, c


def _eval_rot_worker(rot):
    """Eval the shared base mask at a given rotation (for rotation scans)."""
    c = eval_mask(_BASE, rot=rot, xor_mask=_XOR, step=_STEP, key_idx=_KEY, groups=_GRP)
    return rot, c


def default_xor_mask():
    """Reproduce the depth>=4 rule the shipped code uses when _xor_mask is None.
    depth = r % (forest_height+1) = r % 11; xor index increments per (diag,vec)
    in emit order. We just mark which xor instances are depth>=4."""
    # Reconstruct emit order for rot=31 to know each xor's depth.
    return _emit_depths(ORACLE_ROT)


def _emit_depths(rot):
    """Return, in xor emit order for the given rotation, the boolean
    (depth>=4) which is the shipped default for xor_valu."""
    K = K_VEC
    step = 4
    h1 = 11
    perm = [(j - rot) % K for j in range(K)]
    ppos = {perm[p]: p for p in range(K)}
    n_diag = (K + step - 1) // step + ROUNDS - 1
    depths = []
    for diag in range(n_diag):
        for q in range(K):
            j = perm[q]
            r = diag - ppos[j] // step
            if 0 <= r < ROUNDS:
                depths.append((r % h1) >= 4)
    return depths


def sweep_combine(base, pool, xor=None, step=4, key_idx=0, groups=3, rot=ORACLE_ROT):
    args = list(range(N_COMBINE))
    with mp.Pool(pool, initializer=_init,
                 initargs=(base, xor, step, key_idx, groups, rot)) as p:
        res = p.map(_flip_eval, args, chunksize=16)
    return dict(res)


def sweep_xor(base, pool, xor=None, step=4, key_idx=0, groups=3, rot=ORACLE_ROT):
    args = list(range(N_XOR))
    with mp.Pool(pool, initializer=_init,
                 initargs=(base, xor, step, key_idx, groups, rot)) as p:
        res = p.map(_flip_eval_xor, args, chunksize=16)
    return dict(res)


def scan_rotations(base, pool, xor=None, step=4, key_idx=0, groups=3):
    with mp.Pool(pool, initializer=_init,
                 initargs=(base, xor, step, key_idx, groups, ORACLE_ROT)) as p:
        res = p.map(_eval_rot_worker, list(range(K_VEC)))
    return dict(res)


def save_best(mask, count, xor=None, extra=None):
    d = {"count_rot31": count, "combine_mask": [int(b) for b in mask]}
    if xor is not None:
        d["xor_mask"] = [int(b) for b in xor]
    if extra:
        d.update(extra)
    with open(BEST_FILE, "w") as f:
        json.dump(d, f)


def load_best():
    if os.path.exists(BEST_FILE):
        with open(BEST_FILE) as f:
            return json.load(f)
    return None


# ------------------------------------------------------------------ #
def cmd_sweep(args):
    """Day-1 kill test: one single-bit sweep from the seed, report improving
    flips."""
    base = seed_mask(10, 100)
    t0 = time.time()
    base_count = eval_mask(base)
    print(f"seed(10,100) rot={ORACLE_ROT} count={base_count}  "
          f"({time.time()-t0:.2f}s)")
    t0 = time.time()
    res = sweep_combine(base, args.pool)
    wall = time.time() - t0
    improving = sorted([(c, i) for i, c in res.items() if c < base_count])
    print(f"swept {N_COMBINE} combine flips in {wall:.1f}s "
          f"({wall/N_COMBINE*1000:.0f}ms/flip eff)")
    print(f"improving flips: {len(improving)}")
    for c, i in improving[:40]:
        print(f"  flip bit {i:4d} ({'valu->alu' if base[i] else 'alu->valu'})"
              f" -> {c}  (delta {c-base_count})")
    if not improving:
        print("KILL CRITERION: zero improving flips on combine mask.")
    else:
        print(f"GO: best single flip -> {improving[0][0]} "
              f"(delta {improving[0][0]-base_count})")


def cmd_descent(args):
    """Greedy coordinate descent: repeatedly apply improving flips until none
    improve. Includes optional xor-mask sweeps interleaved."""
    prev = load_best()
    if prev and args.resume:
        base = [bool(b) for b in prev["combine_mask"]]
        xor = [bool(b) for b in prev.get("xor_mask")] if prev.get("xor_mask") else None
        best = prev["count_rot31"]
        print(f"resuming from {BEST_FILE}: count={best}")
    else:
        base = seed_mask(10, 100)
        xor = None
        best = eval_mask(base)
        print(f"start seed count={best}")
    save_best(base, best, xor)

    rounds = 0
    while True:
        rounds += 1
        t0 = time.time()
        res = sweep_combine(base, args.pool, xor=xor)
        wall = time.time() - t0
        improving = sorted([(c, i) for i, c in res.items() if c < best])
        if args.xor:
            xres = sweep_xor(base, args.pool, xor=xor)
            ximp = sorted([(c, i) for i, c in xres.items() if c < best])
        else:
            ximp = []
        print(f"[round {rounds}] best={best} combine-improving={len(improving)} "
              f"xor-improving={len(ximp)} ({wall:.1f}s)")
        if not improving and not ximp:
            print("converged: no improving single flip (combine or xor).")
            break
        # Greedily apply improving flips, re-verifying each (interactions).
        applied = 0
        for c, i in improving:
            m = list(base)
            m[i] = not m[i]
            nc = eval_mask(m, xor_mask=xor)
            if nc < best:
                base = m
                best = nc
                applied += 1
                save_best(base, best, xor)
        # xor flips
        for c, i in ximp:
            x = list(xor) if xor is not None else default_xor_mask()
            x[i] = not x[i]
            nc = eval_mask(base, xor_mask=x)
            if nc < best:
                xor = x
                best = nc
                applied += 1
                save_best(base, best, xor)
        print(f"  applied {applied} flips, new best={best}")
        if applied == 0:
            print("no flip survived re-verification (all interacted away).")
            break
    print(f"DESCENT DONE best rot31={best}")
    # full build check
    t0 = time.time()
    full = eval_full(base, xor_mask=xor)
    print(f"FULL 32-rot build of champion: {full}  ({time.time()-t0:.1f}s)")
    save_best(base, best, xor, extra={"full_build": full})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["sweep", "descent"])
    ap.add_argument("--pool", type=int, default=8)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--xor", action="store_true", help="also sweep xor mask")
    args = ap.parse_args()
    if args.cmd == "sweep":
        cmd_sweep(args)
    elif args.cmd == "descent":
        cmd_descent(args)

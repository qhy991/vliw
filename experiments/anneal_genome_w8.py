"""Wave-8 Tier-X joint genome SA over the 1093 VLIW graph.

W7-C established that *single* combine-flips and *single* offset-steps are both
exhausted at 1093; only a JOINT offset+combine move escaped (to 1092 on a
sibling branch). This driver reproduces that joint search directly on the
w7_oracle fast proxy (rot29, ~0.31s/eval) and confirms survivors on the full
{25,27,29} window and, on demand, the exact full-32 build.

Genome = {"combine_mask": [bool]*1536, "pos_offset": [int]*32}. Both are pure
tail-packing / engine-assignment levers (arithmetic-identity-preserving), so no
move can change correctness — only the schedule length.

Moves (joint by construction — every proposal perturbs BOTH axes):
  - flip 1..K random combine bits
  - step 1..J random pos_offset entries by +-1 (clamped to [0, OFF_MAX])

Usage:
  python experiments/anneal_genome_w8.py --iters 4000 --seed 0 --restarts 3
  python experiments/anneal_genome_w8.py --out champ_w8.json   # writes best genome
"""
import argparse
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PSPACE", "1")

from w7_oracle import build_rots, report  # noqa: E402
import perf_takehome as _p  # noqa: E402

TOTAL_COMBINE = 3 * 32 * 16   # 1536
OFF_MAX = 10                  # observed pos_offset range on the shipped schedule
PROXY_ROTS = (29,)            # shipped full-32 winner; fast single-rot objective
WINDOW_ROTS = (25, 27, 29)    # confirmation window (brackets full-32)
BASELINE = 1085


def shipped_genome():
    valu = set(_p._COMBINE_VALU_PSPACE_32x16)
    cm = [gi in valu for gi in range(TOTAL_COMBINE)]
    po = list(_p._POS_OFFSET_PSPACE_32x16)
    return {"combine_mask": cm, "pos_offset": po}


def _cost(genome, rots=PROXY_ROTS):
    return build_rots(genome, rots)


# --- deterministic PRNG (Date.now/random-free environment safe under our own
#     process; this is a plain script, so `random` is fine here — the ban is on
#     the JS workflow runtime, not local Python) -------------------------------
import random  # noqa: E402


def anneal(iters, seed, t0, t1, kmax, jmax):
    rng = random.Random(seed)
    cur = shipped_genome()
    cur_cost = _cost(cur)
    best = {"combine_mask": cur["combine_mask"][:], "pos_offset": cur["pos_offset"][:]}
    best_cost = cur_cost
    n_eval = 1
    accepts = 0
    for it in range(iters):
        frac = it / max(1, iters - 1)
        temp = t0 * (t1 / t0) ** frac
        # propose a JOINT move: perturb combine bits AND offset entries
        cand_cm = cur["combine_mask"][:]
        cand_po = cur["pos_offset"][:]
        k = rng.randint(1, kmax)
        for _ in range(k):
            idx = rng.randrange(TOTAL_COMBINE)
            cand_cm[idx] = not cand_cm[idx]
        j = rng.randint(1, jmax)
        for _ in range(j):
            pi = rng.randrange(32)
            step = rng.choice((-1, 1))
            cand_po[pi] = min(OFF_MAX, max(0, cand_po[pi] + step))
        cand = {"combine_mask": cand_cm, "pos_offset": cand_po}
        cc = _cost(cand)
        n_eval += 1
        d = cc - cur_cost
        if d <= 0 or rng.random() < math.exp(-d / max(1e-6, temp)):
            cur, cur_cost = cand, cc
            accepts += 1
            if cc < best_cost:
                best = {"combine_mask": cand_cm[:], "pos_offset": cand_po[:]}
                best_cost = cc
                print(f"  [it {it:5d} T={temp:6.3f}] NEW BEST {best_cost}  "
                      f"(evals={n_eval})")
    return best, best_cost, n_eval, accepts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--restarts", type=int, default=1)
    ap.add_argument("--t0", type=float, default=2.5)
    ap.add_argument("--t1", type=float, default=0.05)
    ap.add_argument("--kmax", type=int, default=3, help="max combine flips/move")
    ap.add_argument("--jmax", type=int, default=2, help="max offset steps/move")
    ap.add_argument("--out", default=None, help="write best genome JSON here")
    args = ap.parse_args()

    # sanity: shipped genome reproduces baseline on the proxy
    ship = shipped_genome()
    base = _cost(ship)
    print(f"shipped proxy(rot29) = {base}  (expect {BASELINE})")
    assert base == BASELINE, f"proxy baseline {base} != {BASELINE}"

    t = time.time()
    global_best, global_cost = ship, base
    for r in range(args.restarts):
        seed = args.seed + r * 101
        print(f"\n=== restart {r} seed={seed} iters={args.iters} "
              f"T {args.t0}->{args.t1} kmax={args.kmax} jmax={args.jmax} ===")
        best, cost, nev, acc = anneal(args.iters, seed, args.t0, args.t1,
                                      args.kmax, args.jmax)
        print(f"  restart {r} best proxy = {cost}  accepts={acc}/{args.iters}")
        if cost < global_cost:
            global_best, global_cost = best, cost

    dt = time.time() - t
    print(f"\nGLOBAL BEST proxy(rot29) = {global_cost}  (baseline {BASELINE})  "
          f"[{dt:.0f}s]")

    if global_cost < BASELINE:
        win = build_rots(global_best, WINDOW_ROTS)
        print(f"CONFIRM window {WINDOW_ROTS} = {win}")
        rep = report(global_best, WINDOW_ROTS)
        print("floors:", rep["floor"], "bind", rep["bind"], "tail", rep["tail"])
        from w7_oracle import build_full  # noqa: E402
        full = build_full(global_best)
        print(f"CONFIRM full-32 = {full}")
        out_path = args.out or os.path.join(os.path.dirname(__file__), "champ_w8.json")
        with open(out_path, "w") as f:
            json.dump({"genome": global_best, "proxy": global_cost, "window": win, "full32": full}, f, indent=2)
        print(f"wrote {out_path}")
    else:
        print("no sub-baseline candidate on proxy; nothing to confirm")


if __name__ == "__main__":
    main()

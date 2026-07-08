"""Wave-7 joint d3xd4 mask SA from the 1094 graph, multi-rot confirm.

The 1094 shipped masks: D3_GATHER_MASK={0,1,37}, D4_COLD_MASK={6,7,9,16,21,
23,24,25,29,32,35}, B0_CARRY=1. Realized floors are load 1035.5 / valu 1031.5 /
F 1025.1 — near-degenerate, so position (tail packing) is the only lever.

Oracle: min over rots {25,27,29} of a single-rot build (~0.3s each). LESSONS
S10: a single-rot oracle misreads perturbed masks; the 3-rot min is a sound-ish
upper bound. Any oracle < 1094 gets a FULL-32 confirm.
"""
import argparse
import os, json, random, sys, time
sys.path.insert(0, ".")
os.environ["PSPACE"] = "1"
import perf_takehome as P

SHAPE = (10, 2047, 256, 16)
N = 64
# Current shipped 1085 seed from champ_d3d4_joint.json.
D3_0 = [0, 2, 39, 41, 44, 57]
D4_0 = [10, 11, 14, 16, 17, 20, 23, 25, 27, 28, 31, 33]


def build(d3, d4, rots):
    os.environ["D3_GATHER_MASK"] = json.dumps([1 if i in d3 else 0 for i in range(N)])
    os.environ["D4_COLD_MASK"] = json.dumps([1 if i in d4 else 0 for i in range(N)])
    best = 10**9
    for rot in rots:
        kb = P.KernelBuilder()
        kb._rotations = [rot]
        kb.build_kernel(*SHAPE)
        best = min(best, len(kb.instrs))
    return best


def full(d3, d4):
    os.environ["D3_GATHER_MASK"] = json.dumps([1 if i in d3 else 0 for i in range(N)])
    os.environ["D4_COLD_MASK"] = json.dumps([1 if i in d4 else 0 for i in range(N)])
    kb = P.KernelBuilder(); kb.build_kernel(*SHAPE)
    return len(kb.instrs)


def neighbor(d3, d4, rng):
    d3, d4 = set(d3), set(d4)
    which = rng.random()
    tgt = d3 if which < 0.4 else d4
    move = rng.random()
    if move < 0.45 and tgt:
        tgt.discard(rng.choice(list(tgt)))
    elif move < 0.9:
        tgt.add(rng.randrange(N))
    elif tgt:                      # swap
        tgt.discard(rng.choice(list(tgt))); tgt.add(rng.randrange(N))
    return sorted(d3), sorted(d4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1085)
    ap.add_argument("--iters", type=int, default=6000)
    ap.add_argument("--temp", type=float, default=8.0)
    ap.add_argument("--cool", type=float, default=0.997)
    ap.add_argument("--time-budget-s", type=int, default=900)
    ap.add_argument("--rots", type=str, default="25,27,29")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    ROTS = tuple(int(x) for x in args.rots.split(",") if x.strip())
    cur3, cur4 = list(D3_0), list(D4_0)
    cur = build(cur3, cur4, ROTS)
    base_full = full(D3_0, D4_0)
    print(f"seed oracle(min rot{ROTS})={cur}  full32={base_full}", flush=True)
    best = cur; best3, best4 = cur3, cur4
    best_full = base_full
    T = args.temp
    t0 = time.time()
    for it in range(args.iters):
        n3, n4 = neighbor(cur3, cur4, rng)
        if not n4 and not n3:
            continue
        o = build(n3, n4, ROTS)
        d = o - cur
        if d <= 0 or rng.random() < pow(2.718, -d / T):
            cur3, cur4, cur = n3, n4, o
            if o < best:
                f = full(n3, n4)
                if f < best_full:
                    best, best3, best4, best_full = o, n3, n4, f
                    print(f"[{it}] oracle={o} FULL={f}  d3={n3} d4={n4}", flush=True)
        T *= args.cool
        if it % 200 == 199:
            print(f"it={it} cur_oracle={cur} best_full={best_full} T={T:.3f} ({time.time()-t0:.0f}s)", flush=True)
        if time.time() - t0 > args.time_budget_s:
            print(f"time budget hit at it={it}", flush=True); break
    print(f"\nBEST full32={best_full}  (seed {base_full})")
    print(f"D3={best3}\nD4={best4}")


if __name__ == "__main__":
    main()

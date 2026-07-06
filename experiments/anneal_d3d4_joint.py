"""Axis C: JOINT anneal over D3_GATHER_MASK (x) D4_COLD_MASK.

Why joint (measured decomposition on the 1152 graph):
    neither mask -> 1152 ;  d4-only -> 1134 (-18) ;  d3-only -> 1148 (-4) ;
    both -> 1120 (-32).  d3 is worth -4 alone but -14 on top of d4: strong
    d3<->d4 synergy on the load engine (d3 gather ADDS load + packs tail;
    d4 cold-vload REMOVES load). Neither single-axis search sees it; this one
    co-perturbs both masks.

Search signal: the omni rot-27 oracle build (~0.33s) is a *strict upper bound*
on full-32 realized (measured: 24/24 samples had full <= oracle, diff in
[-144, 0]). So oracle < 1120 GUARANTEES full < 1120 (cheap, sound accept). Near
the champion the gap is tight (0..11), so we also full-confirm any candidate
with oracle <= CONFIRM_BAND to catch full-wins the oracle rates slightly high.

Champ gate (a real, landable win):
    full-32 PSPACE=1 < 1120  AND  full-32 PSPACE=0 <= 1187.
Both are checked before we ever record a champ; correctness (parity/algebra/
submission) is run by the orchestrator on the landed mask.

Tie-break at equal oracle realized: prefer lower load floor, then lower tail.
Pareto front (realized vs load) is dumped for other axes.
"""
import argparse, json, math, os, random, time, sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("PSPACE", "1")
import perf_takehome as P

SHAPE = (10, 2 ** 11 - 1, 256, 16)
SLOTS = {"valu": 6, "alu": 12, "load": 2, "flow": 1, "store": 1}
N = 64
ORACLE_ROT = 27

# shipped champions
D3_CHAMP = [0, 1, 2, 3, 4, 37, 39, 40, 46, 54, 58]
D4_CHAMP = [25, 26, 27, 29, 31, 34]


def _mask(idxs):
    a = [0] * N
    for i in idxs:
        a[i] = 1
    return a


def _floors(kb):
    eng = Counter()
    for b in kb.instrs:
        if isinstance(b, dict):
            for e, slots in b.items():
                eng[e] += len(slots)
    fl = {e: eng[e] / SLOTS[e] for e in ("valu", "alu", "load", "flow", "store")}
    fl["F"] = (8 * eng["valu"] + eng["alu"]) / 60.0
    fl["realized"] = len(kb.instrs)
    fl["tail"] = fl["realized"] - max(
        fl["valu"], fl["alu"], fl["load"], fl["flow"], fl["F"])
    return fl


def build(d3, d4, pspace="1", rot=ORACLE_ROT):
    """d3/d4 are bool lists of length 64. rot=None -> full-32 build."""
    os.environ["PSPACE"] = pspace
    os.environ.pop("D3_GATHER_TAIL", None)
    os.environ["D3_GATHER_MASK"] = json.dumps([1 if b else 0 for b in d3])
    os.environ["D4_COLD_MASK"] = json.dumps([1 if b else 0 for b in d4])
    kb = P.KernelBuilder()
    if rot is not None:
        kb._rotations = [rot]
    kb.build_kernel(*SHAPE)
    return kb


def oracle(d3, d4):
    return _floors(build(d3, d4, pspace="1", rot=ORACLE_ROT))


def full(d3, d4, pspace="1"):
    return _floors(build(d3, d4, pspace=pspace, rot=None))


def score(fl):
    # SA objective: minimize oracle realized; tie-break lower load then tail.
    return (fl["realized"], fl["load"], fl["tail"])


def mutate(d3, d4, rng, sparse_bias=0.55):
    """Flip 1-2 bits across the two masks. sparse_bias keeps masks lean
    (prefer clearing a set bit over setting a new one)."""
    nd3, nd4 = d3[:], d4[:]
    k = 1 if rng.random() < 0.72 else 2
    for _ in range(k):
        which = nd3 if rng.random() < 0.5 else nd4
        clear = rng.random() < sparse_bias
        pool = [i for i in range(N) if which[i] == clear]
        if not pool:
            pool = list(range(N))
        i = rng.choice(pool)
        which[i] ^= 1
    return nd3, nd4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=3000)
    ap.add_argument("--restarts", type=int, default=4)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--T0", type=float, default=2.5)
    ap.add_argument("--cooling", type=float, default=0.9985)
    ap.add_argument("--collect", type=int, default=1122,
                    help="collect distinct masks with oracle <= this for full-confirm")
    ap.add_argument("--topk", type=int, default=40,
                    help="max distinct masks to full-confirm (best oracle first)")
    ap.add_argument("--gate1", type=int, default=1120, help="PSPACE=1 champ gate (strict <)")
    ap.add_argument("--gate0", type=int, default=1187, help="PSPACE=0 gate (<=)")
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(__file__), "..", "champ_d3d4_joint.json"))
    ap.add_argument("--pareto", default=os.path.join(
        os.path.dirname(__file__), "..", "d3d4_pareto.jsonl"))
    args = ap.parse_args()

    rng = random.Random(args.seed)
    seed_d3, seed_d4 = _mask(D3_CHAMP), _mask(D4_CHAMP)
    seed_fl = oracle(seed_d3, seed_d4)
    print(f"seed champ: oracle={seed_fl['realized']} load={seed_fl['load']:.1f} "
          f"tail={seed_fl['tail']:.1f}", flush=True)
    sf1 = full(seed_d3, seed_d4, "1")["realized"]
    sf0 = full(seed_d3, seed_d4, "0")["realized"]
    print(f"seed full: PSPACE1={sf1} PSPACE0={sf0}", flush=True)

    # ---- Phase 1: pure-oracle SA, collect distinct low-oracle masks -------- #
    # oracle is a strict upper bound on full realized (measured 24/24), so a low
    # oracle can only under-promise. Collect every distinct mask with oracle <=
    # --collect; batch-confirm the best of them on the slow full build later.
    collected = {}  # (tuple d3, tuple d4) -> (oracle_realized, oracle_load)
    t0 = time.time()
    for rst in range(args.restarts):
        d3, d4 = seed_d3[:], seed_d4[:]
        cur = oracle(d3, d4)
        cur_s = score(cur)
        T = args.T0
        print(f"--- restart {rst} ---", flush=True)
        for it in range(args.iters):
            n3, n4 = mutate(d3, d4, rng)
            fl = oracle(n3, n4)
            s = score(fl)
            d = s[0] - cur_s[0]
            accept = d < 0 or (d == 0 and s < cur_s) or \
                rng.random() < math.exp(-d / max(T, 1e-6))
            if accept:
                d3, d4, cur, cur_s = n3, n4, fl, s
            if fl["realized"] <= args.collect:
                key = (tuple(i for i in range(N) if n3[i]),
                       tuple(i for i in range(N) if n4[i]))
                if key not in collected:
                    collected[key] = (fl["realized"], round(fl["load"], 1))
            T *= args.cooling
            if it % 500 == 0:
                print(f"  r{rst} it{it} T={T:.3f} cur_oracle={cur['realized']} "
                      f"cur_load={cur['load']:.1f} collected={len(collected)} "
                      f"({time.time()-t0:.0f}s)", flush=True)
    print(f"\nphase1 done: {len(collected)} distinct masks with oracle<={args.collect} "
          f"({time.time()-t0:.0f}s)", flush=True)

    # ---- Phase 2: batch full-confirm the best-by-oracle unique masks ------- #
    ranked = sorted(collected.items(), key=lambda kv: (kv[1][0], kv[1][1]))
    ranked = ranked[:args.topk]
    best_full, best_full0, best_masks = sf1, sf0, (D3_CHAMP, D4_CHAMP)
    pf = open(args.pareto, "w")
    pareto = {}  # load -> best realized
    print(f"phase2: full-confirming top {len(ranked)} masks", flush=True)
    for (kd3, kd4), (orc, orcL) in ranked:
        d3, d4 = _mask(kd3), _mask(kd4)
        f1 = full(d3, d4, "1")
        L = round(f1["load"], 1)
        if L not in pareto or f1["realized"] < pareto[L]:
            pareto[L] = f1["realized"]
        rec = {"realized": f1["realized"], "load": L, "tail": round(f1["tail"], 1),
               "oracle": orc, "d3": list(kd3), "d4": list(kd4)}
        f0 = None
        if f1["realized"] < args.gate1:
            f0 = full(d3, d4, "0")["realized"]
            rec["pspace0"] = f0
            gate = "LANDABLE" if f0 <= args.gate0 else f"REJECT(p0={f0})"
            print(f"  full1={f1['realized']} p0={f0} load={L} orc={orc} [{gate}] "
                  f"d3={list(kd3)} d4={list(kd4)}", flush=True)
            if f0 <= args.gate0 and f1["realized"] < best_full:
                best_full, best_full0, best_masks = f1["realized"], f0, (list(kd3), list(kd4))
        pf.write(json.dumps(rec) + "\n")
        pf.flush()
    pf.close()

    print(f"\nBEST full PSPACE1={best_full} PSPACE0={best_full0} (seed {sf1}/{sf0})", flush=True)
    print(f"  d3={best_masks[0]}", flush=True)
    print(f"  d4={best_masks[1]}", flush=True)
    print("Pareto (load -> best realized):", flush=True)
    for L in sorted(pareto):
        print(f"  load={L} realized={pareto[L]}", flush=True)
    verdict = "IMPROVED past 1120" if best_full < args.gate1 else "1120 holds"
    print(f"time={time.time()-t0:.0f}s VERDICT: {verdict}", flush=True)
    with open(args.out, "w") as f:
        json.dump({"best_full1": best_full, "best_full0": best_full0,
                   "d3": best_masks[0], "d4": best_masks[1],
                   "seed_full1": sf1, "seed_full0": sf0,
                   "n_collected": len(collected), "n_confirmed": len(ranked),
                   "verdict": verdict}, f, indent=2)
    print("JOINT_DONE", flush=True)


if __name__ == "__main__":
    main()

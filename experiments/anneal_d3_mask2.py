"""Round 2b: aggressive multi-restart SA over D3_GATHER_MASK, seeded from the
1121 champion. No drain-half bias (round-3 slots {0,1,2,3} proved they matter).
Dual-gate aware: only accepts a new global best if PSPACE=0 <= 1187 too, so we
never chase a PSPACE=1 optimum that fails the landable gate (the sibling-window
blindspot lesson).
"""
import os, sys, json, random, math
sys.path.insert(0, "/mnt/user_dir/shihaichao/qinhaiyan/vliw-w6-d3-sparse")
import perf_takehome as P

CHAMP_POS = [0, 1, 2, 3, 4, 37, 39, 40, 46, 54, 58]
N = 64
CHAMP = [i in CHAMP_POS for i in range(N)]
PSPACE0_GATE = 1187


def realized(mask, pspace="1"):
    os.environ["PSPACE"] = pspace
    os.environ.pop("D3_GATHER_TAIL", None)
    os.environ["D3_GATHER_MASK"] = json.dumps([1 if b else 0 for b in mask])
    kb = P.KernelBuilder()
    kb.build_kernel(10, 2 ** 11 - 1, 256, 16)
    return len(kb.instrs)


def anneal(seed_mask, iters, T0, seed):
    random.seed(seed)
    cur = seed_mask[:]
    cur_c = realized(cur)
    best, best_c = cur[:], cur_c
    T = T0
    for it in range(iters):
        cand = cur[:]
        # multi-bit flips occasionally to jump basins
        k = 1 if random.random() < 0.8 else random.randint(2, 3)
        for _ in range(k):
            cand[random.randint(0, N - 1)] ^= 1
        c = realized(cand)
        d = c - cur_c
        if d <= 0 or random.random() < math.exp(-d / max(T, 1e-6)):
            cur, cur_c = cand, c
            if c < best_c:
                best, best_c = cand[:], c
        T *= 0.997
    return best, best_c


GLOBAL_BEST = CHAMP[:]
GLOBAL_C = realized(CHAMP)
print(f"seed champ 1121 -> {GLOBAL_C}", flush=True)
RESTARTS = int(os.environ.get("SA_RESTARTS", "4"))
ITERS = int(os.environ.get("SA_ITERS", "250"))
for r in range(RESTARTS):
    if r == 0:
        seed_mask = GLOBAL_BEST[:]
    else:
        random.seed(90000 + r)
        seed_mask = [random.random() < 0.20 for _ in range(N)]
    b, bc = anneal(seed_mask, ITERS, T0=2.0 + r, seed=41000 + r * 7)
    pos = [i for i in range(N) if b[i]]
    p0 = realized(b, "0")
    landable = p0 <= PSPACE0_GATE
    print(f"restart {r}: best={bc} pspace0={p0} landable={landable} mask={pos}", flush=True)
    if bc < GLOBAL_C and landable:
        GLOBAL_BEST, GLOBAL_C = b[:], bc
        print(f"  -> NEW GLOBAL BEST {bc} (pspace0 {p0})", flush=True)

pos = [i for i in range(N) if GLOBAL_BEST[i]]
p0 = realized(GLOBAL_BEST, "0")
print(f"\nGLOBAL BEST realized={GLOBAL_C} mask={pos} PSPACE0={p0}", flush=True)
print("SA2_DONE", flush=True)

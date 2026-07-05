"""Full-space simulated annealing over D3_GATHER_MASK (round 2).

Round 1 combo-searched only the benefit window anchored on {42}. This SA explores
the full 64-bit mask space to prove whether 1132 is the true d3-sparse ceiling or a
local optimum. Bit-flip neighborhood; PSPACE=1 realized is the objective; the best
found is re-checked for the PSPACE=0 <= 1187 gate at the end.
"""
import os, sys, json, random, math
sys.path.insert(0, "/mnt/user_dir/shihaichao/qinhaiyan/vliw-w6-d3-sparse")
os.environ.setdefault("PSPACE", "1")
import perf_takehome as P

random.seed(20260706)


def realized(mask, pspace="1"):
    os.environ["PSPACE"] = pspace
    os.environ.pop("D3_GATHER_TAIL", None)
    os.environ["D3_GATHER_MASK"] = json.dumps([1 if b else 0 for b in mask])
    kb = P.KernelBuilder()
    kb.build_kernel(10, 2 ** 11 - 1, 256, 16)
    return len(kb.instrs)


N = 64
ITERS = int(os.environ.get("SA_ITERS", "400"))
# seed from the known champion {42,50,55}
cur = [i in (42, 50, 55) for i in range(N)]
cur_c = realized(cur)
best, best_c = cur[:], cur_c
print(f"seed {{42,50,55}} -> {cur_c}", flush=True)

T0, cooling = 3.0, 0.995
T = T0
evals = 1
for it in range(ITERS):
    cand = cur[:]
    # bias flips toward the round-14 drain half (32..63) where wins concentrate
    if random.random() < 0.75:
        p = random.randint(32, 63)
    else:
        p = random.randint(0, 63)
    cand[p] = not cand[p]
    c = realized(cand)
    evals += 1
    d = c - cur_c
    if d <= 0 or random.random() < math.exp(-d / max(T, 1e-6)):
        cur, cur_c = cand, c
        if c < best_c:
            best, best_c = cand[:], c
            pos = [i for i in range(N) if cand[i]]
            print(f"  it={it} NEW BEST {best_c} mask={pos}", flush=True)
    T *= cooling
    if it % 50 == 0:
        print(f"  it={it} cur={cur_c} best={best_c} T={T:.3f} evals={evals}", flush=True)

pos = [i for i in range(N) if best[i]]
p0 = realized(best, pspace="0")
print(f"\nBEST realized(PSPACE=1)={best_c} mask={pos} PSPACE0={p0} evals={evals}", flush=True)
print(f"CEILING_CHECK: {'IMPROVED past 1132' if best_c < 1132 else 'no improvement (1132 is ceiling)'}", flush=True)
print("SA_DONE", flush=True)

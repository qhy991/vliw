"""Round 3: focused single-run SA from the 1121 champion, 400 iters, dual-gate.
Accepts a new global best only if PSPACE=0 <= 1187 (landable). Prints every
improving PSPACE=1 move + its PSPACE=0 so we never chase a non-landable optimum.
"""
import os, sys, json, random, math
sys.path.insert(0, "/mnt/user_dir/shihaichao/qinhaiyan/vliw-w6-d3-sparse")
import perf_takehome as P
CHAMP_POS = [0, 1, 2, 3, 36, 37, 40, 43, 45, 49, 58]
N = 64
GATE0 = 1187
def realized(mask, ps="1"):
    os.environ["PSPACE"] = ps
    os.environ.pop("D3_GATHER_TAIL", None)
    os.environ["D3_GATHER_MASK"] = json.dumps([1 if b else 0 for b in mask])
    kb = P.KernelBuilder(); kb.build_kernel(10, 2**11 - 1, 256, 16)
    return len(kb.instrs)
random.seed(770077)
cur = [i in CHAMP_POS for i in range(N)]
cur_c = realized(cur)
best, best_c = cur[:], cur_c
best_p0 = realized(best, "0")
print(f"seed 1121 -> {cur_c} (pspace0 {best_p0})", flush=True)
T = 1.5
for it in range(400):
    cand = cur[:]
    k = 1 if random.random() < 0.75 else 2
    for _ in range(k):
        cand[random.randint(0, N-1)] ^= 1
    c = realized(cand)
    d = c - cur_c
    if d <= 0 or random.random() < math.exp(-d / max(T, 1e-6)):
        cur, cur_c = cand, c
        if c < best_c:
            p0 = realized(cand, "0")
            if p0 <= GATE0:
                best, best_c, best_p0 = cand[:], c, p0
                print(f"  it={it} NEW BEST {c} pspace0={p0} mask={[i for i in range(N) if cand[i]]}", flush=True)
            else:
                print(f"  it={it} pspace1={c} REJECTED (pspace0={p0}>{GATE0})", flush=True)
    T *= 0.996
    if it % 80 == 0:
        print(f"  it={it} cur={cur_c} best={best_c} T={T:.3f}", flush=True)
print(f"\nFINAL best={best_c} pspace0={best_p0} mask={[i for i in range(N) if best[i]]}", flush=True)
print("VERDICT:", "IMPROVED past 1121" if best_c < 1121 else "1121 holds (axis converged)", flush=True)
print("SA3_DONE", flush=True)

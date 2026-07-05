import os, sys, json, itertools
sys.path.insert(0, "/mnt/user_dir/shihaichao/qinhaiyan/vliw-w6-d3-sparse")
os.environ.setdefault("PSPACE", "1")
import perf_takehome as P


def realized(idxs):
    os.environ.pop("D3_GATHER_TAIL", None)
    m = [0] * 64
    for i in idxs:
        m[i] = 1
    os.environ["D3_GATHER_MASK"] = json.dumps(m)
    kb = P.KernelBuilder()
    kb.build_kernel(10, 2 ** 11 - 1, 256, 16)
    return len(kb.instrs)


base_set = [42, 50, 55]
print("base {42,50,55} ->", realized(base_set), flush=True)

tight = [42, 44, 50, 55, 57, 49, 51, 53, 56]
best = []
for c in itertools.combinations(tight, 4):
    r = realized(list(c))
    best.append((r, c))
    if r <= 1132:
        print(f"  size4 {c} -> {r}", flush=True)

print("greedy extend {42,50,55}+x:", flush=True)
for x in range(32, 64):
    if x in base_set:
        continue
    r = realized(base_set + [x])
    if r <= 1132:
        print(f"  +{x} -> {r}", flush=True)
    best.append((r, tuple(sorted(base_set + [x]))))

print("TOP:", flush=True)
for r, c in sorted(set(best))[:12]:
    print(f"  {c} real={r} d={r - 1134:+d}", flush=True)
print("GREEDY_DONE", flush=True)

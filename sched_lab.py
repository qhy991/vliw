"""Scheduler R&D harness. Capture the rot=31 op-graph once, then try alternative
scheduling strategies in-memory and compare bundle counts. The op-graph is the
SAME; only the packing changes. Winners must be verified with a full build +
submission_tests.py (correctness), but bundle-count comparison here is exact.

We reimplement the dependency build + a pluggable list-scheduler so we can
experiment without touching perf_takehome.py until we have a winner.
"""
import bisect
import time
from collections import defaultdict

import perf_takehome as P
from perf_takehome import Scheduler, KernelBuilder
from problem import SLOT_LIMITS

SHAPE = (10, 2 ** 11 - 1, 256, 16)
K_VEC, ROUNDS = 32, 16
N_COMBINE = 3 * K_VEC * ROUNDS


def seed():
    return [(gi < 10 or gi >= N_COMBINE - 100) for gi in range(N_COMBINE)]


def capture_ops(rot=31, cmask=None):
    cmask = cmask if cmask is not None else seed()
    cap = {}
    orig = Scheduler.schedule

    def grab(self, ops, key_idx=0):
        # keep the LARGEST op-list seen (the body, not setup)
        if "ops" not in cap or len(ops) > len(cap["ops"]):
            cap["ops"] = list(ops)
            cap["k"] = key_idx
        return orig(self, ops, key_idx)

    kb = KernelBuilder()
    kb._combine_mask = cmask
    kb._rotations = [rot]
    Scheduler.schedule = grab
    try:
        kb.build_kernel(*SHAPE)
    finally:
        Scheduler.schedule = orig
    return cap["ops"], cap["k"]


def build_deps(ops):
    n = len(ops)
    writers = defaultdict(list)
    readers = defaultdict(list)
    for i, op in enumerate(ops):
        for a in op.writes:
            writers[a].append(i)
        for a in op.reads:
            readers[a].append(i)
    deps = [set() for _ in range(n)]
    for i, op in enumerate(ops):
        for a in op.reads:
            ws = writers.get(a)
            if not ws:
                continue
            k = bisect.bisect_left(ws, i)
            if k > 0:
                deps[i].add(ws[k - 1])
        for a in op.writes:
            ws = writers.get(a)
            k = bisect.bisect_left(ws, i)
            pred_w = ws[k - 1] if k > 0 else -1
            if k > 0:
                deps[i].add(ws[k - 1])
            rs = readers.get(a, [])
            lo = bisect.bisect_right(rs, pred_w)
            hi = bisect.bisect_left(rs, i)
            for r in rs[lo:hi]:
                deps[i].add(r)
    return deps


def metrics(ops, deps):
    n = len(ops)
    succ = [0] * n
    hgt = [1] * n
    for i in range(n):
        for d in deps[i]:
            succ[d] += 1
        for d in ops[i].after:
            succ[d] += 1
    for i in range(n - 1, -1, -1):
        b = 1
        for d in deps[i]:
            x = hgt[d] + 1
            if x > b:
                b = x
        hgt[i] = b
    return succ, hgt


def list_schedule(ops, deps, key):
    """Generic greedy list scheduler with a custom key(i) -> sortable.
    Returns bundle count."""
    n = len(ops)
    alldeps = [deps[i] | ops[i].after for i in range(n)]
    dependents = [[] for _ in range(n)]
    indeg = [0] * n
    for i in range(n):
        d = alldeps[i]
        indeg[i] = len(d)
        for p in d:
            dependents[p].append(i)
    sched = [None] * n
    ready = [i for i in range(n) if indeg[i] == 0]
    cur = 0
    placed_total = 0
    while placed_total < n:
        ready.sort(key=key)
        written_this = set()
        slot_count = defaultdict(int)
        placed_idx = []
        leftover = []
        for i in ready:
            op = ops[i]
            if slot_count[op.engine] >= SLOT_LIMITS[op.engine]:
                leftover.append(i)
                continue
            if any(a in written_this for a in op.writes):
                leftover.append(i)
                continue
            slot_count[op.engine] += 1
            for a in op.writes:
                written_this.add(a)
            sched[i] = cur
            placed_idx.append(i)
        if not placed_idx:
            return None
        newly = []
        for i in placed_idx:
            for dep in dependents[i]:
                indeg[dep] -= 1
                if indeg[dep] == 0:
                    newly.append(dep)
        placed_total += len(placed_idx)
        ready = leftover + newly
        cur += 1
    return cur


if __name__ == "__main__":
    t0 = time.time()
    ops, k = capture_ops()
    deps = build_deps(ops)
    succ, hgt = metrics(ops, deps)
    print(f"captured {len(ops)} ops, key_idx={k}  ({time.time()-t0:.1f}s)")

    # baseline key
    key0 = lambda i: (-hgt[i], -succ[i], i)
    t0 = time.time()
    n0 = list_schedule(ops, deps, key0)
    print(f"baseline (-hgt,-succ,i): {n0}  ({time.time()-t0:.2f}s)")

    # Try a battery of static priority keys.
    import problem
    keys = {
        "(-hgt,-succ,i)": lambda i: (-hgt[i], -succ[i], i),
        "(-hgt,i)": lambda i: (-hgt[i], i),
        "(-succ,-hgt,i)": lambda i: (-succ[i], -hgt[i], i),
        "(-hgt,-succ,-eng_scarcity,i)": None,  # placeholder
        "(-hgt*w,-succ,i) w by engine": None,
    }
    # engine scarcity weight: flow(1)>load/store(2)>valu(6)>alu(12); prefer
    # scheduling scarce-engine ops earlier so they don't bottleneck later.
    scarce = {"flow": 5, "load": 4, "store": 4, "valu": 2, "alu": 1}
    keyA = lambda i: (-hgt[i], -scarce[ops[i].engine], -succ[i], i)
    keyB = lambda i: (-scarce[ops[i].engine], -hgt[i], -succ[i], i)
    keyC = lambda i: (-hgt[i] - scarce[ops[i].engine], -succ[i], i)
    for name, key in [("hgt,scarce,succ", keyA),
                      ("scarce,hgt,succ", keyB),
                      ("hgt+scarce,succ", keyC)]:
        n = list_schedule(ops, deps, key)
        print(f"  {name}: {n}  (delta {n-n0 if n else 'FAIL'})")

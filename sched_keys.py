"""Broad automatic search over scheduler priority keys + a few structural
scheduler variants, on the captured rot=31 body op-graph (1217 baseline)."""
import time
from collections import defaultdict

from sched_lab import capture_ops, build_deps, metrics, list_schedule
from problem import SLOT_LIMITS


def main():
    ops, k = capture_ops()
    deps = build_deps(ops)
    succ, hgt = metrics(ops, deps)
    n = len(ops)
    eng = [op.engine for op in ops]
    base = list_schedule(ops, deps, lambda i: (-hgt[i], -succ[i], i))
    print(f"baseline {base}")

    scarce = {"flow": 5, "load": 4, "store": 4, "valu": 2, "alu": 1}
    # generate many keys parametrically
    import itertools
    best = base
    best_name = "baseline"
    tested = 0
    t0 = time.time()
    # weight combos over (hgt, succ, scarce, id-direction)
    for wh in (1, 2, 3):
        for ws in (0, 1, 2):
            for wc in (0, 1, 3, 5):
                for idsign in (1, -1):
                    key = lambda i, wh=wh, ws=ws, wc=wc, idsign=idsign: (
                        -(wh * hgt[i] + wc * scarce[eng[i]]),
                        -ws * succ[i],
                        idsign * i,
                    )
                    n2 = list_schedule(ops, deps, key)
                    tested += 1
                    if n2 and n2 < best:
                        best = n2
                        best_name = f"wh={wh} ws={ws} wc={wc} idsign={idsign}"
                        print(f"  NEW BEST {n2}: {best_name}")
    print(f"tested {tested} keys in {time.time()-t0:.1f}s")
    print(f"BEST {best} ({best_name})")


if __name__ == "__main__":
    main()

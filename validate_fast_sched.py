"""Validate that run_fast produces byte-identical bundles to the original run,
across several rotations and masks. Also times the speedup."""
import random
import time

import perf_takehome as P
from perf_takehome import Scheduler, KernelBuilder

SHAPE = (10, 2 ** 11 - 1, 256, 16)
K_VEC, ROUNDS = 32, 16
N_COMBINE = 3 * K_VEC * ROUNDS


def build_ops(combine_mask, rot, step=4, groups=3):
    """Reproduce the exact (prefix+rnd) op list build_kernel schedules for one
    rotation, by monkeypatching Scheduler.schedule to capture the ops."""
    captured = {}
    orig = Scheduler.schedule

    def cap(self, ops, key_idx=0):
        captured["ops"] = list(ops)
        captured["key_idx"] = key_idx
        return orig(self, ops, key_idx)

    kb = KernelBuilder()
    kb._combine_mask = combine_mask
    kb._step = step
    kb._num_mtmp_groups = groups
    kb._rotations = [rot]
    Scheduler.schedule = cap
    try:
        kb.build_kernel(*SHAPE)
    finally:
        Scheduler.schedule = orig
    return captured["ops"], captured["key_idx"]


def bundles_equal(a, b):
    if len(a) != len(b):
        return False, f"len {len(a)} != {len(b)}"
    for i, (x, y) in enumerate(zip(a, b)):
        if x.keys() != y.keys():
            return False, f"bundle {i} engines {list(x)} != {list(y)}"
        for eng in x:
            if x[eng] != y[eng]:
                return False, f"bundle {i} engine {eng}:\n {x[eng]}\n {y[eng]}"
    return True, "ok"


def main():
    random.seed(0)
    seed = [(gi < 10 or gi >= N_COMBINE - 100) for gi in range(N_COMBINE)]
    masks = {
        "seed(10/100)": seed,
        "all-alu": [False] * N_COMBINE,
        "all-valu": [True] * N_COMBINE,
        "random-a": [random.random() < 0.5 for _ in range(N_COMBINE)],
        "random-b": [random.random() < 0.3 for _ in range(N_COMBINE)],
    }
    rots = [0, 7, 17, 31]
    all_ok = True
    tf = ts = 0.0
    for mname, mask in masks.items():
        for rot in rots:
            ops, key_idx = build_ops(mask, rot)
            t0 = time.time()
            Scheduler.force_slow = True
            slow = Scheduler().schedule(ops, key_idx)
            ts += time.time() - t0
            t0 = time.time()
            Scheduler.force_slow = False
            fast = Scheduler().schedule(ops, key_idx)
            tf += time.time() - t0
            ok, msg = bundles_equal(slow, fast)
            status = "OK " if ok else "MISMATCH"
            print(f"[{status}] {mname:14s} rot={rot:2d} "
                  f"slow={len(slow)} fast={len(fast)}  {msg if not ok else ''}")
            if not ok:
                all_ok = False
    print(f"\nTotal slow time {ts:.1f}s, fast time {tf:.1f}s, "
          f"speedup {ts/tf:.1f}x")
    print("ALL IDENTICAL" if all_ok else "!!! MISMATCH FOUND !!!")


if __name__ == "__main__":
    main()

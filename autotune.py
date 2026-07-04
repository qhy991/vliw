"""Offline autotuner for the VLIW SIMD kernel (perf_takehome.py).

NOT part of the submission path. It drives KernelBuilder with explicit
per-combine engine masks + structural knobs, using len(kb.instrs) as an exact
data-independent cycle oracle, and searches for a mask that beats 1230.

Winners are re-validated with the full 32-rotation build + submission_tests.py.
"""
import argparse
import multiprocessing as mp
import time

import perf_takehome as P

SHAPE = (10, 2 ** 11 - 1, 256, 16)   # forest_height, n_nodes, batch_size, rounds
K_VEC = 32
ROUNDS = 16
N_COMBINE = 3 * K_VEC * ROUNDS       # 1536
N_XOR = K_VEC * ROUNDS               # 512


def build_count(combine_mask=None, xor_mask=None, step=4, key_idx=0,
                num_mtmp_groups=3, rotations=None):
    """Return len(kb.instrs) for the given knobs. rotations=None -> all K
    (full shipped semantics); a list -> only those rotations (fast oracle)."""
    kb = P.KernelBuilder()
    kb._combine_mask = combine_mask
    kb._xor_mask = xor_mask
    kb._step = step
    kb._key_idx = key_idx
    kb._num_mtmp_groups = num_mtmp_groups
    kb._rotations = rotations
    kb.build_kernel(*SHAPE)
    return len(kb.instrs)


def seed_masks_from_headtail(head=10, tail=100):
    """Reproduce exactly the mask the head/tail heuristic produces, so the
    search starts from the known-good 1230 configuration."""
    combine = [(gi < head or gi >= N_COMBINE - tail) for gi in range(N_COMBINE)]
    return combine


# ------- worker for per-rotation measurement / single-rot oracle ------------ #
def _eval_rot(args):
    combine_mask, xor_mask, step, key_idx, groups, rot = args
    t0 = time.time()
    c = build_count(combine_mask, xor_mask, step, key_idx, groups, [rot])
    return rot, c, time.time() - t0


def measure_per_rotation(combine_mask=None, xor_mask=None, step=4, key_idx=0,
                         groups=3, cores=10):
    """Schedule all 32 rotations (in parallel) and report each rotation's
    single-rotation cycle count + timing."""
    args = [(combine_mask, xor_mask, step, key_idx, groups, rot)
            for rot in range(K_VEC)]
    t0 = time.time()
    with mp.Pool(cores) as pool:
        results = pool.map(_eval_rot, args)
    wall = time.time() - t0
    results.sort()
    return results, wall


# ------- engine-occupancy profiler for a single rotation -------------------- #
def profile_rotation(combine_mask=None, xor_mask=None, step=4, key_idx=0,
                     groups=3, rot=0):
    """Build one rotation and return per-bundle engine slot occupancy so we can
    see where alu/valu are idle (windup/drain) vs saturated (middle)."""
    kb = P.KernelBuilder()
    kb._combine_mask = combine_mask
    kb._xor_mask = xor_mask
    kb._step = step
    kb._key_idx = key_idx
    kb._num_mtmp_groups = groups
    kb._rotations = [rot]
    kb.build_kernel(*SHAPE)
    prof = []
    for b in kb.instrs:
        prof.append({eng: len(slots) for eng, slots in b.items()})
    return prof, len(kb.instrs)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="measure")
    ap.add_argument("--cores", type=int, default=10)
    ap.add_argument("--rot", type=int, default=0)
    args = ap.parse_args()

    if args.mode == "profile":
        from problem import SLOT_LIMITS
        seed = seed_masks_from_headtail(10, 100)
        prof, n = profile_rotation(combine_mask=seed, rot=args.rot)
        print(f"rot={args.rot} cycles={n}")
        # bucketed occupancy
        buckets = [(0, 100), (100, 200), (200, 1000), (1000, 1100),
                   (1100, n)]
        for lo, hi in buckets:
            seg = prof[lo:hi]
            if not seg:
                continue
            avg = {}
            for eng in ("alu", "valu", "load", "store", "flow"):
                tot = sum(b.get(eng, 0) for b in seg)
                avg[eng] = tot / len(seg) / SLOT_LIMITS[eng] * 100
            print(f"  [{lo:4d}-{hi:4d}] "
                  + "  ".join(f"{e}={avg[e]:5.1f}%" for e in
                              ("alu", "valu", "load", "store", "flow")))
        # count pure stall bundles (both alu and valu < 1 slot used but not done)
        import sys
        sys.exit(0)

    if args.mode == "measure":
        # 1) verify default full build == 1230 (behavior-preserving refactor)
        t0 = time.time()
        full = build_count()            # rotations=None -> all 32, head/tail heuristic
        print(f"[default full build] CYCLES={full}  ({time.time()-t0:.1f}s)")

        # 2) verify explicit seed mask reproduces the same full build
        seed = seed_masks_from_headtail(10, 100)
        t0 = time.time()
        full_masked = build_count(combine_mask=seed)
        print(f"[seed-mask full build] CYCLES={full_masked}  ({time.time()-t0:.1f}s)")

        # 3) per-rotation single-rot counts under the seed mask
        results, wall = measure_per_rotation(combine_mask=seed, cores=args.cores)
        print(f"[per-rotation, seed mask]  ({wall:.1f}s wall on {args.cores} cores)")
        best = min(results, key=lambda r: r[1])
        for rot, c, dt in results:
            marker = "  <-- BEST" if rot == best[0] else ""
            print(f"  rot={rot:2d}  cycles={c}  ({dt:.1f}s){marker}")
        print(f"BEST single-rot: rot={best[0]} cycles={best[1]}")

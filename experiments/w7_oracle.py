"""W7-D search infrastructure: a fast, reusable build oracle for Wave-7.

The scheduler tries all K=32 vector-order rotations and keeps the tightest
schedule (`build_kernel` in perf_takehome.py). A full 32-rotation build costs
~10s; a single pinned rotation costs ~0.3s. Two facts make the pinned build a
faithful proxy:

  1. Op-counts (and therefore every engine floor) are GENOME-determined and
     rotation-INVARIANT -- rot only changes tail-packing, not the work. So
     load/alu/valu/flow/F are reported once, exact for any rotation.
  2. On the shipped 1093 graph the full-32 winner is rot 29; the {25,27,29}
     window brackets it, so `build_rots` reproduces 1093 in ~1s.

GENOME.  A JSON-serializable dict of KernelBuilder attribute overrides applied
AFTER __init__ and BEFORE build_kernel. Keys are attribute names WITHOUT the
leading underscore (e.g. "combine_mask", "pos_offset", "d3_gather_mask",
"step", "b0_carry"). An empty/None genome reproduces the shipped 1093 build.
Every mask class is a 1-valu-op <-> 8-scalar-op equivalence, so engine masks
never change correctness -- only packing. (Structural scalars like `step` or
`b0_carry` CAN change op-counts; that is fine, floors are re-derived per build.)

Usage:
    from experiments.w7_oracle import build_full, build_rots, report

    build_rots()                      # -> 1093  (fast ~1s proxy)
    build_full()                      # -> 1093  (exact, ~10s)
    report()                          # full metric dict + JSON
    build_rots({"b0_carry": 0})       # eval a candidate genome

CLI:
    python experiments/w7_oracle.py                 # baseline report, asserts 1093
    python experiments/w7_oracle.py --genome g.json # eval a genome file
    python experiments/w7_oracle.py --full          # add exact full-32 cycles
    python experiments/w7_oracle.py --bench          # 100 rot-window evals, time it
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("PSPACE", "1")

from perf_takehome import KernelBuilder
from problem import SLOT_LIMITS

SHAPE = (10, 2 ** 11 - 1, 256, 16)   # forest_height, n_nodes, batch_size->K, rounds
ENGINES = ("alu", "valu", "load", "store", "flow")
BASELINE = 1085
DEFAULT_ROTS = (25, 27, 29)


def _apply_genome(kb, genome):
    """Assign genome overrides onto a fresh KernelBuilder.

    Keys are attribute names without the leading underscore. Unknown keys raise
    (a silent no-op would let a mistyped gene masquerade as the baseline).
    """
    if not genome:
        return
    for key, val in genome.items():
        attr = key if key.startswith("_") else "_" + key
        if not hasattr(kb, attr):
            raise KeyError(f"unknown genome key {key!r} (KernelBuilder has no {attr})")
        setattr(kb, attr, val)


def _build(genome, rotations):
    """Build once with the given genome and rotation restriction; return the
    KernelBuilder (already built)."""
    kb = KernelBuilder()
    _apply_genome(kb, genome)
    if rotations is not None:
        kb._rotations = list(rotations)
    kb.build_kernel(*SHAPE)
    return kb


def _op_counts(kb):
    tot = {e: 0 for e in ENGINES}
    for b in kb.instrs:
        for e in ENGINES:
            tot[e] += len(b.get(e, []))
    return tot


def build_full(genome=None):
    """Exact objective: full 32-rotation build, min cycles. ~10s."""
    kb = _build(genome, None)
    return len(kb.instrs)


def build_rots(genome=None, rots=DEFAULT_ROTS):
    """Fast proxy: build each rotation in `rots` singly, return the min cycles.

    Op-counts are rotation-invariant, so a single build per rotation gives the
    exact schedule length for that rotation; the min over the window brackets
    the full-32 winner on the shipped graph (=1093)."""
    best = None
    for rot in rots:
        kb = _build(genome, [rot])
        c = len(kb.instrs)
        if best is None or c < best:
            best = c
    return best


def report(genome=None, rots=DEFAULT_ROTS, full=False):
    """Full metric dict for a genome. JSON-serializable.

    Floors are exact (op-counts rotation-invariant). `cycles` is the rot-window
    min (fast proxy); pass full=True to also compute the exact full-32 cycles.

    Returns:
      cycles      -- min over `rots` (fast proxy for the realized schedule)
      per_rot     -- {rot: cycles} for each rotation in the window
      ops         -- {engine: op count}
      floor       -- {engine: op count / slot limit}  (load is the binding floor)
      F           -- (alu+valu) / (12+6), the co-binding arith floor
      bind        -- name of the max-floor engine
      max_floor   -- the binding floor value
      tail        -- cycles - max_floor (scheduling slack above the floor)
      full_cycles -- exact full-32 min (only when full=True)
    """
    per_rot = {}
    kb_last = None
    for rot in rots:
        kb = _build(genome, [rot])
        per_rot[rot] = len(kb.instrs)
        kb_last = kb
    cycles = min(per_rot.values())

    ops = _op_counts(kb_last)                      # rotation-invariant
    floor = {e: ops[e] / SLOT_LIMITS[e] for e in ENGINES}
    F = (ops["alu"] + ops["valu"]) / (SLOT_LIMITS["alu"] + SLOT_LIMITS["valu"])
    bind = max(ENGINES, key=lambda e: floor[e])
    max_floor = floor[bind]

    out = {
        "cycles": cycles,
        "per_rot": per_rot,
        "ops": ops,
        "floor": {e: round(floor[e], 1) for e in ENGINES},
        "F": round(F, 1),
        "bind": bind,
        "max_floor": round(max_floor, 1),
        "tail": round(cycles - max_floor, 1),
    }
    if full:
        out["full_cycles"] = build_full(genome)
    return out


def _fmt(rep):
    lines = [
        f"cycles     = {rep['cycles']}   (rot-window min, per_rot={rep['per_rot']})",
    ]
    if "full_cycles" in rep:
        lines.append(f"full_cycles = {rep['full_cycles']}  (exact full-32)")
    lines.append(
        "floors     : "
        + "  ".join(f"{e}={rep['floor'][e]}" for e in ENGINES)
    )
    lines.append(
        f"F          = {rep['F']}   bind={rep['bind']} @ {rep['max_floor']}"
        f"   tail={rep['tail']}"
    )
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="W7-D build oracle")
    ap.add_argument("--genome", help="JSON file with a genome dict")
    ap.add_argument("--rots", default=",".join(map(str, DEFAULT_ROTS)),
                    help="comma-separated rotation window (default 25,27,29)")
    ap.add_argument("--full", action="store_true",
                    help="also compute exact full-32 cycles")
    ap.add_argument("--bench", action="store_true",
                    help="run 100 rot-window evals and report wall time")
    ap.add_argument("--json", action="store_true", help="print JSON only")
    args = ap.parse_args()

    genome = None
    if args.genome:
        with open(args.genome) as f:
            genome = json.load(f)
    rots = tuple(int(x) for x in args.rots.split(","))

    if args.bench:
        t = time.time()
        n = 100
        for _ in range(n):
            build_rots(genome, rots)
        dt = time.time() - t
        print(f"{n} rot-window evals ({len(rots)} rots each): {dt:.1f}s "
              f"({dt / n * 1000:.0f} ms/eval)  -- limit 600s")
        assert dt < 600, "rot-window eval budget exceeded (>10 min)"
        return

    rep = report(genome, rots, full=args.full)
    if args.json:
        print(json.dumps(rep))
    else:
        print(_fmt(rep))
        print("\n" + json.dumps(rep))

    if genome is None:
        # Baseline must reproduce 1093 exactly on both the proxy and the full build.
        assert rep["cycles"] == BASELINE, \
            f"rot-window proxy {rep['cycles']} != baseline {BASELINE}"
        if args.full:
            assert rep["full_cycles"] == BASELINE, \
                f"full-32 {rep['full_cycles']} != baseline {BASELINE}"
        print(f"\nOK: baseline reproduces {BASELINE}")


if __name__ == "__main__":
    main()

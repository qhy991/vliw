#!/usr/bin/env python3
"""E2: D4_COLD partial-k sweep — cold vload mux (no 128w resident nb table).

Usage:
  python experiments/probe_e2_d4_coldtable.py          # footprint + k sweep
  python experiments/probe_e2_d4_coldtable.py --check  # parity on best k only
"""
import argparse
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("PSPACE", "1")

import perf_takehome as P

SLOTS = {"valu": 6, "alu": 12, "load": 2, "flow": 1, "store": 1}
FOREST_HEIGHT, ROUNDS, BATCH = 10, 16, 256
BASELINE = 1151


def floors(kb):
    eng = Counter()
    for b in kb.instrs:
        if isinstance(b, dict):
            for e, slots in b.items():
                eng[e] += len(slots)
    fl = {e: eng[e] / SLOTS[e] for e in ("valu", "alu", "load", "flow", "store")}
    fl["F"] = (8 * eng["valu"] + eng["alu"]) / 60.0
    fl["_ops"] = dict(eng)
    fl["realized"] = len(kb.instrs)
    fl["bind"] = max(fl["load"], fl["alu"], fl["valu"], fl["flow"], fl["F"])
    return fl


def build(k):
    os.environ["D4_COLD"] = str(k)
    os.environ["D4_COLD_MASK"] = "[]"
    os.environ.pop("D4_MUX", None)
    kb = P.KernelBuilder()
    kb.build_kernel(FOREST_HEIGHT, 2 ** 11 - 1, BATCH, ROUNDS)
    return kb


def baseline_scratch():
    os.environ.pop("D4_COLD", None)
    os.environ["D4_COLD_MASK"] = "[]"
    os.environ.pop("D4_MUX", None)
    kb = P.KernelBuilder()
    kb.build_kernel(FOREST_HEIGHT, 2 ** 11 - 1, BATCH, ROUNDS)
    return kb.scratch_ptr, 1536 - kb.scratch_ptr


def check_correct(k):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))
    from frozen_problem import Machine, build_mem_image, reference_kernel2, Tree, Input, N_CORES

    os.environ["D4_COLD"] = str(k)
    os.environ.pop("D4_MUX", None)
    forest = Tree.generate(FOREST_HEIGHT)
    inp = Input.generate(forest, BATCH, ROUNDS)
    mem = build_mem_image(forest, inp)
    kb = P.KernelBuilder()
    kb.build_kernel(forest.height, len(forest.values), len(inp.indices), ROUNDS)
    m = Machine(mem, kb.instrs, kb.debug_info(), n_cores=N_CORES)
    m.enable_pause = m.enable_debug = False
    m.run()
    for ref_mem in reference_kernel2(mem):
        pass
    ivp = ref_mem[6]
    ok = m.mem[ivp:ivp + len(inp.values)] == ref_mem[ivp:ivp + len(inp.values)]
    return ok, m.cycle


def footprint():
    ptr, free = baseline_scratch()
    print(f"Baseline @1151: scratch_ptr={ptr}/1536  free={free}\n")
    print("=== E2 cold-table resident footprint ===")
    # d4_stash preserves the lo-subtree result while the hi-subtree reuses bc0/bc1.
    cold_words = 5 * 8
    print("  d4_lo + d4_hi + d4_bc0 + d4_bc1 + d4_stash = 40w "
          "(vs #26 128w nb table)")
    print(f"  fits in free={free}: {'YES' if cold_words <= free else 'NO'}\n")


def sweep(ks):
    print(f"{'k':>3}  {'realized':>8}  {'load':>7}  {'alu':>7}  {'valu':>7}  "
          f"{'flow':>7}  {'bind':>7}  {'Δload':>6}  {'Δreal':>6}")
    base_kb = build(0)
    base_fl = floors(base_kb)
    best = (BASELINE + 1, 0, None)
    for k in ks:
        kb = build(k)
        fl = floors(kb)
        dload = base_fl["_ops"]["load"] - fl["_ops"]["load"]
        dreal = fl["realized"] - BASELINE
        mark = "  ←" if fl["realized"] < BASELINE else ""
        print(f"{k:3d}  {fl['realized']:8d}  {fl['load']:7.1f}  {fl['alu']:7.1f}  "
              f"{fl['valu']:7.1f}  {fl['flow']:7.1f}  {fl['bind']:7.1f}  "
              f"{dload:+6d}  {dreal:+6d}{mark}")
        if fl["realized"] < best[0]:
            best = (fl["realized"], k, fl)
    print()
    if best[1]:
        print(f"Best sweep: k={best[1]} realized={best[0]} (baseline {BASELINE})")
    else:
        print("No k improved over baseline realized.")
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="parity-check best k")
    ap.add_argument("--ks", default="0,14,15,16,17,18,19,20,21,22,32,64")
    args = ap.parse_args()
    footprint()
    ks = [int(x) for x in args.ks.split(",")]
    best = sweep(ks)
    if args.check and best[1]:
        ok, cyc = check_correct(best[1])
        print(f"parity k={best[1]}: ok={ok} machine_cycles={cyc}")


if __name__ == "__main__":
    main()

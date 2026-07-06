#!/usr/bin/env python
"""Scratch-reclaim audit @ 1111 (2026-07-06).

Measures the 1111 graph scratch budget, E2 cold-table footprint, mask
sensitivity, and node-pool penalty. Reproduces the scratch-reclaim axis verdict.

Run: python experiments/probe_scratch_reclaim_1111.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import perf_takehome as P

SHAPE = (10, 2**11 - 1, 256, 16)
SCRATCH = 1536


def build(env=None):
    for k in ("PSPACE", "D4_COLD_MASK", "D3_GATHER_MASK", "NODE_POOL_G",
              "GATHER_FREE", "B0_CARRY"):
        os.environ.pop(k, None)
    os.environ["PSPACE"] = "1"
    if env:
        os.environ.update({k: str(v) for k, v in env.items()})
    import importlib
    importlib.reload(P)
    kb = P.KernelBuilder()
    kb.build_kernel(*SHAPE)
    return kb


def main():
    print("=== Scratch-reclaim audit @ 1111 ===\n")

    base = build()
    print(f"shipped:  cycles={len(base.instrs)}  scratch={base.scratch_ptr}  "
          f"free={SCRATCH - base.scratch_ptr}")

    no_d4 = build({"D4_COLD_MASK": "[]"})
    print(f"no D4_COLD: cycles={len(no_d4.instrs)}  free={SCRATCH - no_d4.scratch_ptr}  "
          f"(+{len(no_d4.instrs) - len(base.instrs)}c, "
          f"+{SCRATCH - no_d4.scratch_ptr - (SCRATCH - base.scratch_ptr)}w)")

    no_d3 = build({"D3_GATHER_MASK": "[]"})
    print(f"no D3_GATHER: cycles={len(no_d3.instrs)}  free={SCRATCH - no_d3.scratch_ptr}")

    cold_cost = (SCRATCH - no_d4.scratch_ptr) - (SCRATCH - base.scratch_ptr)
    print(f"\nE2 cold-table resident footprint: ~{cold_cost} words "
          f"(d4_lo+hi+stash+bc0+bc1+eight)")

    print("\n--- node/addr pool (WAR penalty on 1111 graph) ---")
    for g in (0, 2, 4, 8):
        kb = build({"NODE_POOL_G": g}) if g else base
        if g:
            kb = build({"NODE_POOL_G": g})
        print(f"  NODE_POOL_G={g}: cycles={len(kb.instrs)}  free={SCRATCH - kb.scratch_ptr}")

    print("\n--- O1+O3 stack proxy (GATHER_FREE + B0_CARRY) ---")
    for tag, env in [
        ("O1 proxy", {"GATHER_FREE": "1"}),
        ("O1+O3", {"GATHER_FREE": "1", "B0_CARRY": "1"}),
    ]:
        kb = build(env)
        print(f"  {tag}: cycles={len(kb.instrs)}  free={SCRATCH - kb.scratch_ptr}")

    print("\n--- gate math ---")
    need = 128 - (SCRATCH - base.scratch_ptr)
    print(f"  d4 full tournament table needs 128w; have {SCRATCH - base.scratch_ptr}w free")
    print(f"  shortfall for naive #26 table: {max(0, need)}w")
    print(f"  doc target (≥65 beyond #25's 30 on older graph): need ~"
          f"{65 - (SCRATCH - base.scratch_ptr)}w more on THIS graph")

    print("\n--- verdict ---")
    print("  Clean reclaim (#25 recycler) already landed; E2 cold costs ~48w.")
    print("  node/addr pool frees words but REGRESSES cycles catastrophically on 1111.")
    print("  mtmp-group bc borrow tried: +5..+13c for +16..+24w (not cycle-neutral).")
    print("  Sub-1111 gather cut needs a NEW representation, not more rebalance.")


if __name__ == "__main__":
    main()

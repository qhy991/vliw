#!/usr/bin/env python
"""O1+O3 stack union test @ 1111 (2026-07-06).

O1 proxy: GATHER_FREE=1 deletes all depth>=4 node fetches (wrong output;
measures the load-cut schedule where alu becomes binding).
O3 lever: B0_CARRY=1 eliminates redundant b0=& extracts (correct when gathers
live; on GATHER_FREE graph measures stackable alu-floor drop).

Run: python experiments/probe_o1o3_stack.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import perf_takehome as P

SLOTS = {"load": 2, "alu": 12, "valu": 6, "flow": 1, "store": 2}
SHAPE = (10, 2**11 - 1, 256, 16)


def profile(env: dict) -> dict:
    for k in ("GATHER_FREE", "B0_CARRY", "PSPACE"):
        os.environ.pop(k, None)
    os.environ["PSPACE"] = "1"
    os.environ.update({k: str(v) for k, v in env.items()})
    import importlib
    importlib.reload(P)
    kb = P.KernelBuilder()
    kb.build_kernel(*SHAPE)
    eng = {e: 0 for e in SLOTS}
    for b in kb.instrs:
        if isinstance(b, dict):
            for e, slots in b.items():
                eng[e] += len(slots)
    floors = {e: eng[e] / SLOTS[e] for e in SLOTS if e != "store"}
    F = (8 * eng["valu"] + eng["alu"]) / 60.0
    bind = max(floors["load"], floors["alu"], floors["valu"], F)
    tail = len(kb.instrs) - bind
    return {
        "cycles": len(kb.instrs),
        "load": floors["load"],
        "alu": floors["alu"],
        "valu": floors["valu"],
        "flow": floors["flow"],
        "F": F,
        "bind": bind,
        "tail": tail,
        "eng": eng,
    }


def main():
    cases = [
        ("baseline", {}),
        ("O3 alone (B0_CARRY)", {"B0_CARRY": "1"}),
        ("O1 alone (GATHER_FREE)", {"GATHER_FREE": "1"}),
        ("O1+O3 union", {"GATHER_FREE": "1", "B0_CARRY": "1"}),
    ]
    rows = []
    print("=== O1+O3 stack union @ 1111 (PSPACE=1) ===\n")
    print(f"{'case':<26} {'cyc':>5} {'load':>7} {'alu':>7} {'valu':>7} {'F':>7} {'bind':>7} {'tail':>6}")
    print("-" * 78)
    for name, env in cases:
        r = profile(env)
        rows.append((name, r))
        print(
            f"{name:<26} {r['cycles']:5d} {r['load']:7.1f} {r['alu']:7.1f} "
            f"{r['valu']:7.1f} {r['F']:7.1f} {r['bind']:7.1f} {r['tail']:6.1f}"
        )

    base, o3, o1, union = [r for _, r in rows]
    print("\n=== stacking arithmetic ===")
    d_o1 = base["cycles"] - o1["cycles"]
    d_o3_on_o1 = o1["cycles"] - union["cycles"]
    d_union = base["cycles"] - union["cycles"]
    d_o3_alone = base["cycles"] - o3["cycles"]
    print(f"  O1 gain on baseline:        {base['cycles']} -> {o1['cycles']}  ({d_o1:+d}c)")
    print(f"  O3 gain on load-cut (O1):   {o1['cycles']} -> {union['cycles']}  ({d_o3_on_o1:+d}c)")
    print(f"  Union vs baseline:          {base['cycles']} -> {union['cycles']}  ({d_union:+d}c)")
    print(f"  O3 alone on baseline:       {base['cycles']} -> {o3['cycles']}  ({-d_o3_alone:+d}c, expect REGRESS)")
    print(f"  Additivity check:           O1+O3 stacked = {d_o1}+{d_o3_on_o1} = {d_o1+d_o3_on_o1}c  (union {d_union}c)")

    print("\n=== orthogonality (engine floors, union vs O1 alone) ===")
    for e in ("load", "alu", "valu", "F"):
        v_o1 = o1["load"] if e == "load" else o1["alu"] if e == "alu" else o1["valu"] if e == "valu" else o1["F"]
        v_u = union["load"] if e == "load" else union["alu"] if e == "alu" else union["valu"] if e == "valu" else union["F"]
        print(f"  {e:4s}: O1={v_o1:.1f}  union={v_u:.1f}  delta={v_u-v_o1:+.1f}")

    ok_stack = d_o3_on_o1 > 0 and o1["load"] < o1["alu"] and union["alu"] < o1["alu"]
    ok_ortho = abs(union["load"] - o1["load"]) < 0.1
    print(f"\n=== verdict ===")
    print(f"  O3 stacks on O1 load-cut: {'PASS' if ok_stack else 'FAIL'}  (O3-on-O1 {-d_o3_on_o1:+d}c)")
    print(f"  O3 does not touch load floor on union: {'PASS' if ok_ortho else 'FAIL'}")
    print(f"  O3 alone regresses baseline: {'PASS' if o3['cycles'] > base['cycles'] else 'FAIL'}  ({o3['cycles']} vs {base['cycles']})")
    if ok_stack and ok_ortho and o3["cycles"] > base["cycles"]:
        print("  STACK UNION: PASS — enable B0_CARRY=1 after O1 lands load < alu.")
    else:
        print("  STACK UNION: needs review")


if __name__ == "__main__":
    main()

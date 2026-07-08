#!/usr/bin/env python3
"""Decompose the binding valu floor (@1085) by opcode/role/depth.

Goal: find the largest STRUCTURALLY reducible valu bucket, not shuffle it.
"""
from __future__ import annotations

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("PSPACE", "1")

import perf_takehome as P

SHAPE = (10, 2047, 256, 16)
SLOTS = {"load": 2, "valu": 6, "alu": 12, "flow": 1}


def main() -> None:
    kb_cls = P.KernelBuilder
    orig_emit = kb_cls._emit_vec_round
    orig_op = kb_cls.op
    ctx = {"depth": None, "phase": "setup"}

    def wrapped_emit(self, v, c, depth, j=0, **kw):
        prev = ctx["depth"]
        ctx["depth"] = depth
        ctx["phase"] = "body"
        try:
            return orig_emit(self, v, c, depth, j=j, **kw)
        finally:
            ctx["depth"] = prev

    valu_by_opcode = Counter()
    valu_by_depth_opcode = Counter()
    all_by_engine = Counter()

    def wrapped_op(self, engine, args, *, reads=(), writes=()):
        all_by_engine[engine] += 1
        if engine == "valu":
            opcode = args[0] if isinstance(args, tuple) and args else "?"
            valu_by_opcode[str(opcode)] += 1
            valu_by_depth_opcode[(ctx["depth"], str(opcode))] += 1
        return orig_op(self, engine, args, reads=reads, writes=writes)

    kb_cls._emit_vec_round = wrapped_emit
    kb_cls.op = wrapped_op
    try:
        kb = kb_cls()
        kb._rotations = [29]
        kb.build_kernel(*SHAPE)
    finally:
        kb_cls._emit_vec_round = orig_emit
        kb_cls.op = orig_op

    eng = Counter()
    for b in kb.instrs:
        for e, slots in b.items():
            eng[e] += len(slots)
    print("=== bundled engine floors @", len(kb.instrs), "===")
    for e in SLOTS:
        print(f"  {e:5s} ops={eng[e]:6d} floor={eng[e]/SLOTS[e]:7.1f}")
    F = (8 * eng["valu"] + eng["alu"]) / 60
    print(f"  F=(8*valu+alu)/60 = {F:.1f}")
    print()

    print("=== emitted valu ops by opcode (single rot29 emit) ===")
    total_valu = sum(valu_by_opcode.values())
    for opc, n in valu_by_opcode.most_common():
        print(f"  {opc:14s} {n:6d}  ({100*n/total_valu:5.1f}%)  ~floor {n/6:7.1f}")
    print(f"  TOTAL emitted valu = {total_valu}")
    print()

    print("=== valu ops by (depth, opcode) top 25 ===")
    for (d, opc), n in valu_by_depth_opcode.most_common(25):
        print(f"  depth={str(d):>4} {opc:14s} {n:6d}  ~floor {n/6:7.1f}")
    print()

    print("=== structural reduction potential (if opcode fully eliminated) ===")
    for opc, n in valu_by_opcode.most_common():
        new_valu = eng["valu"] - n
        print(f"  drop all '{opc}': valu floor {eng['valu']/6:.1f} -> {new_valu/6:.1f}")


if __name__ == "__main__":
    main()

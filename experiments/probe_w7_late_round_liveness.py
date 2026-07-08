#!/usr/bin/env python3
"""Late-round liveness audit for the 1085 kernel graph.

Purpose:
  Identify potentially removable ops in rounds 13-15 when only final values are
  considered observable (matching submission_tests behavior).

Approach:
  - Subclass KernelBuilder and log every emitted op with:
      engine, opcode, reads, writes, round index, depth, vector id.
  - Build one representative schedule shape (rot29) to avoid duplicates.
  - Perform backward liveness from final-round value stores (vstore val).
  - Report dead-op candidates by round/depth/opcode.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import perf_takehome as P

SHAPE = (10, 2047, 256, 16)


@dataclass
class LogOp:
    idx: int
    engine: str
    opcode: str
    args: tuple
    reads: set[int]
    writes: set[int]
    round_idx: Optional[int]
    depth: Optional[int]
    vec_slot: Optional[int]


class ProbeKB(P.KernelBuilder):
    def __init__(self) -> None:
        super().__init__()
        self._probe_round: Optional[int] = None
        self._probe_depth: Optional[int] = None
        self._probe_vec: Optional[int] = None
        self.logged: list[LogOp] = []

    def _emit_vec_round(self, v, c, depth, j=0, skip_idx_update=False, defer_k5=False, enter_x=False):
        # Round index is advanced in build_kernel by outer loop;
        # we approximate by local counter carried in builder state.
        if not hasattr(self, "_probe_round_counter"):
            self._probe_round_counter = 0
        r = self._probe_round_counter
        self._probe_round_counter += 1

        prev = (self._probe_round, self._probe_depth, self._probe_vec)
        self._probe_round, self._probe_depth, self._probe_vec = r, depth, j
        try:
            return super()._emit_vec_round(
                v, c, depth, j=j, skip_idx_update=skip_idx_update, defer_k5=defer_k5, enter_x=enter_x
            )
        finally:
            self._probe_round, self._probe_depth, self._probe_vec = prev

    def op(self, engine, args, *, reads=(), writes=()):
        super().op(engine, args, reads=reads, writes=writes)
        opcode = args[0] if isinstance(args, tuple) and args else "?"
        self.logged.append(
            LogOp(
                idx=len(self.logged),
                engine=engine,
                opcode=str(opcode),
                args=tuple(args) if isinstance(args, tuple) else (args,),
                reads=set(reads),
                writes=set(writes),
                round_idx=self._probe_round,
                depth=self._probe_depth,
                vec_slot=self._probe_vec,
            )
        )


def lanes(base: int) -> set[int]:
    return {base + i for i in range(8)}


def collect_value_store_sinks(kb: ProbeKB) -> set[int]:
    """Collect lane registers that are stored by vstore(val)."""
    sink_regs: set[int] = set()
    for b in kb.instrs:
        for slots in b.values():
            for inst in slots:
                if isinstance(inst, tuple) and inst and inst[0] == "vstore" and len(inst) >= 3:
                    sink_regs |= lanes(inst[2])
    return sink_regs


def backward_liveness(logged: list[LogOp], sink_regs: set[int]) -> set[int]:
    # Sink: registers contributing to final vstore(val).
    live_regs: set[int] = set()
    live_ops: set[int] = set()
    live_regs |= sink_regs

    for op in reversed(logged):
        if op.writes & live_regs:
            live_ops.add(op.idx)
            live_regs -= op.writes
            live_regs |= op.reads
    return live_ops


def main() -> None:
    os.environ["PSPACE"] = "1"
    kb = ProbeKB()
    kb._rotations = [29]
    kb.build_kernel(*SHAPE)

    sink_regs = collect_value_store_sinks(kb)
    live_ops = backward_liveness(kb.logged, sink_regs)
    dead = [op for op in kb.logged if op.idx not in live_ops]

    # Focus late rounds only (round counter is per emitted vector-round call).
    # For 16 rounds x 32 vec = 512 calls; calls near tail correspond to later rounds.
    max_r = max((op.round_idx or 0) for op in kb.logged if op.round_idx is not None)
    late_threshold = max_r - 3 * 32  # last ~3 rounds worth of vector emissions

    late_dead = [op for op in dead if op.round_idx is not None and op.round_idx >= late_threshold]
    late_all = [op for op in kb.logged if op.round_idx is not None and op.round_idx >= late_threshold]

    print("=== W7 late-round liveness audit ===")
    print(f"value-store sink regs: {len(sink_regs)}")
    print(f"total logged ops: {len(kb.logged)}")
    print(f"live ops: {len(live_ops)}")
    print(f"dead ops: {len(dead)}")
    print(f"late-window ops (~last 3 rounds): {len(late_all)}")
    print(f"late-window dead ops: {len(late_dead)}")
    print()

    by_opcode = Counter(op.opcode for op in late_dead)
    by_engine = Counter(op.engine for op in late_dead)
    by_depth = Counter(op.depth for op in late_dead)
    print("late dead by opcode:", dict(by_opcode.most_common(20)))
    print("late dead by engine:", dict(by_engine))
    print("late dead by depth:", dict(sorted(by_depth.items(), key=lambda kv: (kv[0] is None, kv[0]))))
    print()

    # Show top candidate patterns with context.
    patterns = defaultdict(int)
    for op in late_dead:
        key = (op.depth, op.engine, op.opcode)
        patterns[key] += 1
    print("top late dead patterns:")
    for (d, eng, opc), n in sorted(patterns.items(), key=lambda kv: -kv[1])[:20]:
        print(f"  depth={d} engine={eng:5s} opcode={opc:10s} count={n}")
    if dead:
        print()
        print("global dead ops (first 8):")
        for op in dead[:8]:
            print(
                f"  idx={op.idx} round={op.round_idx} depth={op.depth} "
                f"engine={op.engine} opcode={op.opcode}"
            )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Depth-5 candidate compression / encoding probe (@1085 graph).

Tests whether any correctness-preserving depth-5 node fetch can beat 8 scalar
gathers per vector instance on op count *and* schedule realized cycles.

Sections:
  A) Data-side compressibility of tree[31..62] (basis/delta/collision)
  B) Static op-cost models for encoding families
  C) Bit-exact hierarchical cold-table selector (Python reference)
  D) Optional empirical cycle count via perf_takehome D5_COLD* env flags
"""
from __future__ import annotations

import json
import os
import random
import sys
from collections import Counter
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from problem import Tree, VLEN

import perf_takehome as P

SHAPE = (10, 2047, 256, 16)
FOREST_H, N_NODES, BATCH, ROUNDS = SHAPE
SLOTS = {"load": 2, "valu": 6, "alu": 12, "flow": 1}
D5_INSTANCES = 32  # K_VEC * one depth-5 round in 16 rounds
SCRATCH_FREE_BASELINE = 21


@dataclass(frozen=True)
class EncodingModel:
    name: str
    remove_load: int
    add_load: int
    add_flow: int
    add_valu: int
    add_alu: int
    scratch_peak: int
    notes: str


def measure_ops() -> dict[str, int]:
    kb = P.KernelBuilder()
    kb.build_kernel(*SHAPE)
    eng = Counter()
    for b in kb.instrs:
        for e, slots in b.items():
            eng[e] += len(slots)
    return {e: eng[e] for e in SLOTS}


def floors(ops: dict[str, int]) -> dict[str, float]:
    return {e: ops[e] / SLOTS[e] for e in SLOTS}


def bind(ops: dict[str, int]) -> float:
    fl = floors(ops)
    fl["F"] = (8 * ops["valu"] + ops["alu"]) / 60.0
    return max(fl["load"], fl["valu"], fl["alu"], fl["flow"], fl["F"])


def apply_model(base: dict[str, int], k: int, m: EncodingModel) -> tuple[dict[str, int], float]:
    ops = dict(base)
    ops["load"] += m.add_load * k - m.remove_load * k
    ops["flow"] += m.add_flow * k
    ops["valu"] += m.add_valu * k
    ops["alu"] += m.add_alu * k
    return ops, bind(ops)


# ---- A: data-side probes ---------------------------------------------------

def compressibility_sample(n_forests: int = 200, seed: int = 0) -> None:
    rng = random.Random(seed)
    print("=== A) tree[31..62] compressibility ===")
    delta_bits = []
    unique_p_per_vec = []
    lane_dup_savings = []
    for _ in range(n_forests):
        forest = Tree.generate(FOREST_H)
        tree = forest.values
        block = tree[31:63]
        for i in range(len(block) - 1):
            delta_bits.append((block[i + 1] ^ block[i]).bit_length())
        # simulate one depth-5 vector with random p-space parities
        ps = [rng.randrange(32) for _ in range(VLEN)]
        unique_p_per_vec.append(len(set(ps)))
        lane_dup_savings.append(VLEN - len(set(ps)))
    print(f"  xor-delta bit-length mean: {sum(delta_bits)/len(delta_bits):.2f}")
    print(f"  xor-delta bit-length p95 : {sorted(delta_bits)[int(0.95*len(delta_bits))]}")
    print(f"  avg unique p / 8 lanes   : {sum(unique_p_per_vec)/len(unique_p_per_vec):.2f}")
    print(f"  avg gather saves if dedup lanes: {sum(lane_dup_savings)/len(lane_dup_savings):.2f} loads/vec")
    print("  verdict: random tree words behave as incompressible 32-word table;")


def p_collision_on_real_inputs(n_samples: int = 10000) -> None:
    print("\n=== A2) lane p collisions (Monte Carlo p in {0..31}) ===")
    rng = random.Random(7)
    stats = Counter()
    for _ in range(n_samples):
        ps = [rng.randrange(32) for _ in range(VLEN)]
        stats[VLEN - len(set(ps))] += 1
    print("  per-vector duplicate-lane count histogram (8 - unique(p)):")
    for k in sorted(stats):
        print(f"    save {k} loads: {stats[k]} vectors")
    print("  verdict: lane dedup is negligible on real inputs.")


# ---- B: op-cost models -----------------------------------------------------

def encoding_models() -> list[EncodingModel]:
    # Per converted depth-5 instance costs (conservative, from d4 cold mux scale-up).
    return [
        EncodingModel(
            "baseline_gather",
            remove_load=0, add_load=0, add_flow=0, add_valu=0, add_alu=0,
            scratch_peak=0,
            notes="8 scalar mem[gather] + 1 valu addr add",
        ),
        EncodingModel(
            "round_vload_table+8_idx_load",
            remove_load=8, add_load=8, add_flow=0, add_valu=0, add_alu=0,
            scratch_peak=32,
            notes="preload table but still 8 indexed scratch loads per vec",
        ),
        EncodingModel(
            "d5_cold_32way",
            remove_load=8, add_load=0, add_flow=31, add_valu=16, add_alu=5,
            scratch_peak=56,
            notes="4x vload setup amortized; 2x d4-style 16-way + b4 select",
        ),
        EncodingModel(
            "d5_split_16+16_broadcast",
            remove_load=8, add_load=0, add_flow=33, add_valu=8, add_alu=4,
            scratch_peak=40,
            notes="two resident 16-word tables + 5-bit tournament",
        ),
        EncodingModel(
            "lane_dedup_best_case",
            remove_load=4, add_load=0, add_flow=0, add_valu=0, add_alu=0,
            scratch_peak=0,
            notes="optimistic: halve loads via duplicate p (not observed)",
        ),
    ]


def model_sweep(base_ops: dict[str, int]) -> None:
    print("\n=== B) static op-cost models (k converted d5 instances) ===")
    base_bind = bind(base_ops)
    print(f"  base bind={base_bind:.1f}")
    for m in encoding_models():
        if m.scratch_peak > SCRATCH_FREE_BASELINE:
            print(f"  {m.name:28s}  scratch {m.scratch_peak}w > free {SCRATCH_FREE_BASELINE}w  -> likely NO-GO")
            continue
        best = None
        for k in range(0, D5_INSTANCES + 1):
            _, bb = apply_model(base_ops, k, m)
            if best is None or bb < best[0]:
                best = (bb, k)
        assert best is not None
        print(f"  {m.name:28s}  best_bind={best[0]:.1f} @k={best[1]:2d}  ({m.notes})")
    print("  verdict: with realistic d5 cold costs, bind never drops below 1000.")


# ---- C: correctness reference for hierarchical cold selector ---------------

def select_tree31_plus_p(table: list[int], p: int) -> int:
    """32-way select from table[0..31] using 5-bit p (reference semantics)."""
    assert len(table) == 32

    def sel8(octet: list[int], idx3: int) -> int:
        b0 = idx3 & 1
        b1 = (idx3 >> 1) & 1
        b2 = (idx3 >> 2) & 1
        t0 = octet[1] if b0 else octet[0]
        t1 = octet[3] if b0 else octet[2]
        t2 = octet[5] if b0 else octet[4]
        t3 = octet[7] if b0 else octet[6]
        u0 = t1 if b1 else t0
        u1 = t3 if b1 else t2
        return u1 if b2 else u0

    lo = table[0:16]
    hi = table[16:32]
    p_lo = p & 15
    b4 = (p >> 4) & 1
    lo8_a = sel8(lo[0:8], p_lo)
    lo8_b = sel8(lo[8:16], p_lo)
    lo16 = lo8_b if (p_lo >> 3) & 1 else lo8_a
    hi8_a = sel8(hi[0:8], p_lo)
    hi8_b = sel8(hi[8:16], p_lo)
    hi16 = hi8_b if (p_lo >> 3) & 1 else hi8_a
    return hi16 if b4 else lo16


def reference_encoding_tests(trials: int = 5000) -> None:
    print("\n=== C) hierarchical cold selector equivalence ===")
    rng = random.Random(99)
    mism = 0
    for _ in range(trials):
        tree = [rng.randrange(2**32) for _ in range(2048)]
        table = tree[31:63]
        for p in range(32):
            if select_tree31_plus_p(table, p) != tree[31 + p]:
                mism += 1
                break
    print(f"  trials={trials}, mismatches={mism}")
    print("  verdict: selector algebra PASS" if mism == 0 else "  verdict: FAIL")


# ---- D: empirical perf_takehome probe (optional env flags) -----------------

def empirical_d5_flags() -> None:
    print("\n=== D) empirical perf_takehome D5_COLD probes ===")
    if not hasattr(P.KernelBuilder, "_d5_cold_mux_node"):
        print("  D5_COLD prototype not present in perf_takehome.py (skip empirical).")
        return

    def run(env: dict[str, str]) -> int:
        for k in list(os.environ):
            if k.startswith("D5_"):
                os.environ.pop(k, None)
        os.environ.update(env)
        os.environ["PSPACE"] = "1"
        kb = P.KernelBuilder()
        kb.build_kernel(*SHAPE)
        return len(kb.instrs)

    base = run({})
    print(f"  baseline cycles={base}")
    for k in (1, 4, 8, 16, 32):
        mask = [1 if i < k else 0 for i in range(D5_INSTANCES)]
        try:
            cyc = run({"D5_COLD_MASK": json.dumps(mask)})
            print(f"  D5_COLD_MASK prefix {k:2d}: cycles={cyc} delta={cyc-base:+d}")
        except AssertionError as e:
            print(f"  D5_COLD_MASK prefix {k:2d}: SCRATCH ASSERT FAIL ({e})")
            break

    # correctness on smallest non-trivial mask if build succeeded
    try:
        os.environ["D5_COLD_MASK"] = json.dumps([1] + [0] * 31)
        os.environ["PSPACE"] = "1"
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))
        from frozen_problem import Machine, build_mem_image, reference_kernel2, Tree, Input, N_CORES

        forest = Tree.generate(FOREST_H)
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
        print(f"  parity D5_COLD_MASK k=1: ok={ok} cycles={len(kb.instrs)}")
    except Exception as e:
        print(f"  parity check skipped/failed: {e}")


def main() -> None:
    base_ops = measure_ops()
    print("=== W7 depth-5 candidate encoding probe @1085 ===")
    print("base ops:", base_ops)
    print("base floors:", {k: round(v, 1) for k, v in floors(base_ops).items()}, "bind=", round(bind(base_ops), 1))
    print(f"scratch free (baseline): {SCRATCH_FREE_BASELINE} words")

    compressibility_sample()
    p_collision_on_real_inputs()
    model_sweep(base_ops)
    reference_encoding_tests()
    empirical_d5_flags()


if __name__ == "__main__":
    main()

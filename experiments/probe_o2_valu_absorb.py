"""O2 axis probe: is any valu/F algebraic elimination worth landing at 1111?

Two questions, both answered NO on the shipped 1111 graph:

  (A) SATURATION: is valu ever the binding engine? If valu never binds (alone or
      in the load-idle tail), removing valu ops is absorbed with zero cycle payoff.
  (B) SENSITIVITY: does dropping valu ops actually lower realized cycles? cycles ==
      len(kb.instrs) is deterministic, so we can measure the schedule's response to
      a synthetic valu cut (correctness intentionally broken; we only read cycles).

Run: python experiments/probe_o2_valu_absorb.py
"""
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from perf_takehome import KernelBuilder

CAP = {"load": 2, "alu": 12, "valu": 6, "flow": 1, "store": 1}


def engine_floors(kb):
    e = defaultdict(int)
    for b in kb.instrs:
        for k, s in b.items():
            e[k] += len(s)
    F = (8 * e["valu"] + e["alu"]) / 60
    return e, F


def part_A():
    kb = KernelBuilder(); kb.build_kernel(10, 2047, 256, 16)
    e, F = engine_floors(kb)
    print("=== (A) engine floors on shipped 1111 graph ===")
    for eng in ("load", "alu", "valu", "flow"):
        print(f"  {eng:5s} ops={e[eng]:6d} floor={e[eng]/CAP[eng]:.1f}")
    print(f"  F=(8*valu+alu)/60 floor={F:.1f}")

    valu_sole = 0            # valu at cap, load AND alu below cap -> only valu binds
    tail_load_idle = 0       # load below cap (tail / windup / drain)
    valu_bind_tail = 0       # in those, valu binds (valu full, alu not)
    alu_bind_tail = 0
    hist = Counter()
    for b in kb.instrs:
        u = {k: len(b.get(k, [])) for k in CAP}
        hist[u["valu"]] += 1
        if u["valu"] >= CAP["valu"] and u["load"] < CAP["load"] and u["alu"] < CAP["alu"]:
            valu_sole += 1
        if u["load"] < CAP["load"]:
            tail_load_idle += 1
            if u["valu"] >= CAP["valu"] and u["alu"] < CAP["alu"]:
                valu_bind_tail += 1
            if u["alu"] >= CAP["alu"] and u["valu"] < CAP["valu"]:
                alu_bind_tail += 1
    print(f"  cycles where valu is the SOLE binder : {valu_sole}   <- 0 => valu cut absorbed")
    print(f"  load-idle tail cycles                : {tail_load_idle}")
    print(f"    of those, valu-bound               : {valu_bind_tail}")
    print(f"    of those, alu-bound                : {alu_bind_tail}")
    print(f"  valu-slot histogram (slots:ncyc)     : {dict(sorted(hist.items()))}")


def part_B():
    print("\n=== (B) realized-cycle response to a synthetic valu cut ===")

    def measure(skip_frac):
        kb = KernelBuilder()
        orig = kb.v_muladd
        st = {"n": 0}

        def patched(dest, a, b, c):
            st["n"] += 1
            if (st["n"] % 1000) / 1000.0 < skip_frac:
                return  # drop the muladd -> removes a valu op
            return orig(dest, a, b, c)

        kb.v_muladd = patched
        kb.build_kernel(10, 2047, 256, 16)
        e, _ = engine_floors(kb)
        return len(kb.instrs), e["valu"]

    print("  skip_frac  cycles  valu  valu_floor")
    for f in (0.0, 0.25, 0.5, 0.9, 1.0):
        cyc, valu = measure(f)
        print(f"  {f:8.2f}  {cyc:6d}  {valu:5d}  {valu/6:8.0f}")
    print("  cycles NON-DECREASING as valu drops => valu is not binding; cuts are absorbed.")


if __name__ == "__main__":
    part_A()
    part_B()
    print("\nVERDICT: O2 NO-GO @1111 (load 1083.5 binds; valu 1027 sub-floor, -56c).")
    print("Resurrection: land O1(load)+O3(alu) below ~1027 first, then re-price O2.")

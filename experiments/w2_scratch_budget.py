"""#13 mem spill: scratch budget analysis for rem-history rings."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from perf_takehome import KernelBuilder, SCRATCH_SIZE, VLEN

V = VLEN


def analyze():
    kb = KernelBuilder()
    kb.build_kernel(10, 2047, 256, 16)
    used = kb.scratch_ptr
    free = SCRATCH_SIZE - used
    print(f"scratch used: {used} / {SCRATCH_SIZE}  (free: {free} words)")
    print(f"per-vector footprint: 4 vectors × 8 lanes = 32 words/vec")
    print(f"K_VEC=32 -> 32 * 32 = 1024 words for idx/val/node/addr")
    print()
    for n_hist in (1, 2, 3):
        need = n_hist * V * 32  # n_hist rem vectors across 32 lane-vectors
        print(f"phase-2 rem history depth={n_hist}: +{need} words  "
              f"({'FITS' if need <= free else 'NEEDS SPILL'}, gap={need-free})")
    print()
    # store engine headroom
    store_ops = sum(
        len(b.get("store", [])) for b in kb.instrs if isinstance(b, dict)
    )
    cycles = len(kb.instrs)
    print(f"build cycles: {cycles}")
    print(f"store ops: {store_ops}  (capacity ~{cycles * 2} slots, "
          f"util {100*store_ops/(cycles*2):.1f}%)")
    print()
    print("mem spill proposal: vstore rem after traverse in d0/d1 windows;")
    print("vload before d2/d3 mux. Estimate +32 store +32 load per rem ring.")


if __name__ == "__main__":
    analyze()

"""Exhaustive single-bit-flip scan of the p-space combine mask at 1093.

For each of the 1536 combine instances, flip its engine bit and measure rot29
(the verified fast oracle == full-32 at the seed). Reports every flip that does
not regress. Parallel across cores. This definitively answers whether any single
bit improves the shipped mask.
"""
import json, os, sys
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["PSPACE"] = "1"
import perf_takehome as P

SHAPE = (10, 2 ** 11 - 1, 256, 16)
K, ROUNDS = 32, 16
N = 3 * K * ROUNDS
ORACLE = 29
CHAMP = set(P._COMBINE_VALU_PSPACE_32x16)
BASE = [i in CHAMP for i in range(N)]


def ev(mask, rot=ORACLE):
    kb = P.KernelBuilder()
    kb._combine_mask = list(mask)
    kb._rotations = [rot]
    kb.build_kernel(*SHAPE)
    return len(kb.instrs)


def flip(i):
    m = list(BASE)
    m[i] = not m[i]
    return i, ev(m)


def main():
    base = ev(BASE)
    print(f"base rot{ORACLE}={base}", flush=True)
    results = []
    with ProcessPoolExecutor(max_workers=int(os.environ.get("W", "24"))) as ex:
        for i, c in ex.map(flip, range(N), chunksize=8):
            results.append((i, c))
            if c <= base:
                mark = "IMPROVE" if c < base else "flat"
                print(f"  flip {i} ({'valu->alu' if BASE[i] else 'alu->valu'}): "
                      f"rot={c} [{mark}]", flush=True)
    results.sort(key=lambda x: x[1])
    print("\nbest 10 flips:", results[:10], flush=True)
    improves = [(i, c) for i, c in results if c < base]
    print(f"\n{len(improves)} single-flip improvements", flush=True)
    with open("single_flip_scan.json", "w") as f:
        json.dump({"base": base, "results": results}, f)


if __name__ == "__main__":
    main()

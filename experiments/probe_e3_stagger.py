#!/usr/bin/env python3
"""E3: sweep diagonal stagger knobs @ 1152 baseline (PSPACE=1).

Sweeps _step (uniform p//step offsets) and _key_idx. Uses oracle rot=27 for
speed, then confirms any improvement with full 32 rotations.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("PSPACE", "1")

import perf_takehome as P

SHAPE = (10, 2 ** 11 - 1, 256, 16)
ORACLE_ROT = 27
BASELINE = 1152


def build(*, step=None, key_idx=None, pos_offset=None, rotations=None):
    kb = P.KernelBuilder()
    if step is not None:
        kb._step = step
    if key_idx is not None:
        kb._key_idx = key_idx
    if pos_offset is not None:
        kb._pos_offset = pos_offset
    kb._rotations = rotations if rotations is not None else [ORACLE_ROT]
    kb.build_kernel(*SHAPE)
    return len(kb.instrs)


def main():
    t0 = time.time()
    print(f"E3 stagger probe @ baseline {BASELINE} (oracle rot={ORACLE_ROT})")
    print(f"shipped default: step=4 key_idx=0 pos_offset=PSPACE winner\n")

    best = BASELINE
    best_cfg = "default"

    # Uniform diagonal: pos_off[p] = p // step
    print("=== step sweep (uniform p//step, key_idx=0) ===")
    for step in range(1, 9):
        cyc = build(step=step, key_idx=0, pos_offset=[p // step for p in range(32)])
        mark = " ***" if cyc < best else (" !" if cyc > BASELINE else "")
        print(f"  step={step}  cycles={cyc}{mark}")
        if cyc < best:
            best, best_cfg = cyc, f"step={step}"

    print("\n=== key_idx sweep (shipped pos_offset, step=4) ===")
    for key in range(5):
        cyc = build(key_idx=key)
        mark = " ***" if cyc < best else (" !" if cyc > BASELINE else "")
        print(f"  key_idx={key}  cycles={cyc}{mark}")
        if cyc < best:
            best, best_cfg = cyc, f"key_idx={key}"

    print("\n=== step=1 vs shipped offset (mixed) ===")
    cyc_ship = build()
    cyc_s1 = build(step=1, pos_offset=[p for p in range(32)])
    print(f"  shipped offset step=4: {cyc_ship}")
    print(f"  uniform step=1:       {cyc_s1}")

    if best < BASELINE:
        print(f"\n>>> oracle best {best} ({best_cfg}) — confirming full-32...")
        # re-build best config with full rotations
        if best_cfg.startswith("step="):
            s = int(best_cfg.split("=")[1])
            full = build(step=s, key_idx=0,
                          pos_offset=[p // s for p in range(32)],
                          rotations=list(range(32)))
        else:
            k = int(best_cfg.split("=")[1])
            full = build(key_idx=k, rotations=list(range(32)))
        print(f"  full-32 confirm: {full}")
        best = min(best, full)
    else:
        print(f"\n>>> no oracle improvement (best={best})")

    print(f"\nVerdict: {'GO' if best < BASELINE else 'NO-GO'} "
          f"(best={best}, delta={BASELINE - best}) [{time.time()-t0:.0f}s]")


if __name__ == "__main__":
    main()

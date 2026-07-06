"""Tail-axis (O4) SA over per-position emit offsets ONLY (op-count invariant).
Fixed d3/d4 masks (shipped 1111 graph). NO combine/extract changes (those are
engine shuffles -> forbidden on the tail axis).

Oracle = min over a WINDOW of rotations, not a single fixed rot. The shipped
offset was tuned with a rot=27-only oracle, but a perturbed offset shifts the
argmin rotation (measured: neighbors best at rots 25-29, rot27 misreads +228c).
A single-rot oracle therefore never searched the joint (offset x rotation)
space. We use a 5-rot window centered on 27.
"""
import json, math, os, random, time, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import perf_takehome as P

SHAPE = (10, 2047, 256, 16)
K = 32
CHAMP = os.path.join(os.path.dirname(__file__), "champ_pos_offset.json")
SEED_OFF = list(P._POS_OFFSET_PSPACE_32x16)


def ev_rots(off, rots):
    best = 10 ** 9
    for rot in rots:
        kb = P.KernelBuilder()
        kb._pos_offset = list(off)
        kb._rotations = [rot]
        kb.build_kernel(*SHAPE)
        best = min(best, len(kb.instrs))
    return best


def full(off):
    kb = P.KernelBuilder()
    kb._pos_offset = list(off)
    kb.build_kernel(*SHAPE)
    return len(kb.instrs)


def neighbor(off, rng):
    off = list(off)
    for _ in range(rng.randint(1, 3)):
        p = rng.randrange(K)
        off[p] = max(0, off[p] + rng.choice((-1, 1, -2, 2)))
    return off


def load_seed():
    if os.path.exists(CHAMP):
        with open(CHAMP) as f:
            d = json.load(f)
        return list(d["offsets"]), f"champ({d.get('full','?')})"
    return list(SEED_OFF), "shipped"


def main():
    iters = int(os.environ.get("ITERS", "3000"))
    T0 = float(os.environ.get("T0", "2.0"))
    seed = int(os.environ.get("SEED", "2026"))
    win = int(os.environ.get("WIN", "2"))   # oracle half-window
    rng = random.Random(seed)
    off, src = load_seed()

    base_full = full(SEED_OFF)
    center = 27
    rots = list(range(center - win, center + win + 1))
    cur = ev_rots(off, rots)
    best = cur; best_off = list(off); best_full = base_full
    print(f"seed {src}: oracle{rots}={cur}  shipped FULL={base_full}", flush=True)

    T = T0; cooling = (0.02 / T0) ** (1.0 / iters)
    t0 = time.time(); accepts = 0
    for it in range(iters):
        no = neighbor(off, rng)
        c = ev_rots(no, rots)
        d = c - cur
        if d <= 0 or rng.random() < math.exp(-d / max(T, 1e-6)):
            off, cur = no, c; accepts += 1
            if c < best:
                best, best_off = c, list(no)
                print(f"[it {it} T={T:.2f}] NEW BEST oracle={c} ({time.time()-t0:.0f}s)", flush=True)
        T *= cooling
        if it % 250 == 249:
            fc = full(best_off)
            if fc < best_full:
                best_full = fc
                with open(CHAMP, "w") as f:
                    json.dump({"full": fc, "offsets": best_off}, f)
                print(f"  it={it} SAVED full={fc}", flush=True)
            print(f"  it={it} T={T:.3f} cur={cur} best_oracle={best} best_FULL={fc} "
                  f"acc={accepts/(it+1):.2f} ({time.time()-t0:.0f}s)", flush=True)
    fc = full(best_off)
    print(f"\nBEST oracle={best}  FULL={fc}  (shipped {base_full})", flush=True)
    if fc < base_full:
        with open(CHAMP, "w") as f:
            json.dump({"full": fc, "offsets": best_off}, f)
        print("saved", CHAMP)


if __name__ == "__main__":
    main()

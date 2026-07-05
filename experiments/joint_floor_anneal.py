"""dir #31 E1 -- JOINT load+alu floor-drop anneal.

Standalone driver on top of experiments/omni_anneal.py. The mechanism (see the
Wave-5 plan): the load floor (1065) BINDS while alu (1036.7) sits 28c below, so
any *lone* const_flow load cut is capped by the alu wall (Rule A) and any *lone*
xor alu->valu flip is absorbed (alu is sub-floor). Neither lever moves realized
alone -- which is why every prior flat-realized anneal was stuck at 1151.

This driver co-searches the two mask classes that live on the two binding
engines and, crucially, accepts on a JOINT-FLOOR score
    score = w1*max(load, alu) + w2*F + w3*realized
so SA climbs toward simultaneous floor reduction across the realized plateau
instead of only on realized (which is flat until BOTH floors move together).
realized stays the hard champ gate: we only ever *ship* a genome whose full-32
realized < 1151 AND which passes the real machine-vs-reference check.

xor is restricted to depth<4 positions: depth>=4 XORs are correctly pinned on
valu (they pack against the gather rounds) -- the seed marks those True, and we
freeze every True-in-seed index so the proposer never touches them.
"""
import argparse, json, math, os, random, time, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
import omni_anneal as OA

ORACLE_ROT = OA.ORACLE_ROT


def build_pins(genome):
    """xor depth>=4 positions are True in the seed (depth>=4 -> valu). Pin them
    so the proposer never flips them; only depth<4 (seed False) positions move."""
    xor_seed = genome.get("xor")
    if xor_seed is None:
        return set()
    return {i for i, v in enumerate(xor_seed) if v}  # True == depth>=4 == pinned


class PinnedProposer(OA.Proposer):
    """Same as omni Proposer but forbids flipping pinned indices of a class."""
    def __init__(self, active, sizes, rng, pins):
        super().__init__(active, sizes, rng)
        self.pins = pins  # {class_name: set(pinned idx)}

    def mutate(self, genome):
        g = {k: (list(v) if isinstance(v, list) else v)
             for k, v in genome.items()}
        name = self.rng.choices(self.active, weights=self.pick_wts, k=1)[0]
        spec = OA.CLASSES[name]
        if spec.kind == "mask":
            mask = g[name]
            pinned = self.pins.get(name, set())
            for _ in range(self.rng.randint(1, 4)):
                to_alu = self.rng.random() < spec.flip_bias  # True->False
                cands = [i for i, b in enumerate(mask)
                         if b == to_alu and i not in pinned]
                if not cands:
                    cands = [i for i in range(len(mask)) if i not in pinned]
                if not cands:
                    break
                w = [self.wts[name][i] for i in cands]
                i = self.rng.choices(cands, weights=w, k=1)[0]
                mask[i] = not mask[i]
        elif spec.kind == "offset":
            off = g[name]
            for _ in range(self.rng.randint(1, 2)):
                p = self.rng.randrange(len(off))
                off[p] = max(0, off[p] + self.rng.choice((-1, 1)))
        else:
            lo = spec.lo
            hi = spec.hi if spec.hi is not None else lo + 8
            g[name] = min(hi, max(lo, g[name] + self.rng.choice((-1, 1))))
        return g


def joint_score(fl, w1, w2, w3):
    """dir #31 objective: pull the two binding floors toward each other while
    still rewarding realized. max(load,alu) is what realized actually chases."""
    return w1 * max(fl["load"], fl["alu"]) + w2 * fl["F"] + w3 * fl["realized"]


def floors_oracle(genome):
    """Floors of the fast single-rotation oracle build (SA inner loop)."""
    return OA.floors(OA.build(genome, rot=ORACLE_ROT))


def anneal(active, iters, out, seed, restarts, T0, cooling,
           w1, w2, w3, confirm_every):
    rng = random.Random(seed)
    genome0, sizes = OA.build_seed(active)
    pins = {"xor": build_pins(genome0)} if "xor" in active else {}
    n_pin = len(pins.get("xor", set()))
    print(f"active={active} sizes={sizes} xor_pinned(depth>=4)={n_pin} "
          f"xor_free(depth<4)={sizes.get('xor', 0) - n_pin}", flush=True)

    fl0 = floors_oracle(genome0)
    seed_full = OA.ev_full(genome0)
    print(f"seed: oracle_realized={fl0['realized']} FULL32={seed_full} "
          f"l={fl0['load']:.1f} a={fl0['alu']:.1f} v={fl0['valu']:.1f} "
          f"F={fl0['F']:.1f} score={joint_score(fl0, w1, w2, w3):.2f}",
          flush=True)

    prop = PinnedProposer(active, sizes, rng, pins)
    global_best_full = seed_full
    global_best_genome = {k: (list(v) if isinstance(v, list) else v)
                          for k, v in genome0.items()}
    shipped = False

    for rst in range(restarts):
        genome = {k: (list(v) if isinstance(v, list) else v)
                  for k, v in genome0.items()}
        cur_fl = floors_oracle(genome)
        cur_score = joint_score(cur_fl, w1, w2, w3)
        best_realized = cur_fl["realized"]
        T, t0 = T0, time.time()
        print(f"--- restart {rst} (T0={T0}) ---", flush=True)
        for it in range(iters):
            ng = prop.mutate(genome)
            fl = floors_oracle(ng)
            s = joint_score(fl, w1, w2, w3)
            d = s - cur_score
            if d <= 0 or rng.random() < math.exp(-d / max(T, 1e-6)):
                genome, cur_score, cur_fl = ng, s, fl
                # champ gate: realized improvement on the oracle triggers a
                # full-32 confirm; only ship if full-32 < 1151 AND correct.
                if fl["realized"] < best_realized:
                    best_realized = fl["realized"]
                    fc = OA.ev_full(ng)
                    tag = ""
                    if fc < global_best_full:
                        ok, _ = OA.check_correct(ng)
                        if ok:
                            global_best_full = fc
                            global_best_genome = {
                                k: (list(v) if isinstance(v, list) else v)
                                for k, v in ng.items()}
                            flf = OA.floors(OA.build(ng, full=True))
                            OA.save_champ(out, global_best_genome, active,
                                          fl["realized"], fc, flf, True)
                            shipped = True
                            tag = f"  SHIPPED FULL32={fc} (correct)"
                        else:
                            tag = f"  !! FULL32={fc} INCORRECT"
                    print(f"[r{rst} it{it} T={T:.2f}] oracle={fl['realized']} "
                          f"FULL32={fc} l={fl['load']:.1f} a={fl['alu']:.1f} "
                          f"v={fl['valu']:.1f} F={fl['F']:.1f} "
                          f"score={s:.1f} ({time.time()-t0:.0f}s){tag}",
                          flush=True)
            T *= cooling
            if confirm_every and it % confirm_every == confirm_every - 1:
                print(f"  r{rst} it={it} T={T:.3f} score={cur_score:.1f} "
                      f"l={cur_fl['load']:.1f} a={cur_fl['alu']:.1f} "
                      f"best_realized={best_realized} best_FULL={global_best_full} "
                      f"({time.time()-t0:.0f}s)", flush=True)

    print(f"\nBEST FULL32={global_best_full} (seed_full={seed_full}) "
          f"shipped={shipped}", flush=True)
    return global_best_genome, global_best_full, seed_full, shipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--classes", default="const_flow,xor,combine,offset")
    ap.add_argument("--iters", type=int, default=5000)
    ap.add_argument("--restarts", type=int, default=3)
    ap.add_argument("--seed", type=int, default=31031)
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(__file__), "..", "champ_joint_floor.json"))
    ap.add_argument("--T0", type=float, default=3.0)
    ap.add_argument("--cooling", type=float, default=0.9994)
    ap.add_argument("--w1", type=float, default=1.0)  # max(load,alu)
    ap.add_argument("--w2", type=float, default=0.5)  # F
    ap.add_argument("--w3", type=float, default=2.0)  # realized
    ap.add_argument("--confirm-every", type=int, default=500)
    args = ap.parse_args()

    active = [c.strip() for c in args.classes.split(",") if c.strip()]
    for c in active:
        if c not in OA.CLASSES:
            ap.error(f"unknown class {c!r}")
    anneal(active, args.iters, args.out, args.seed, args.restarts,
           args.T0, args.cooling, args.w1, args.w2, args.w3,
           args.confirm_every)


if __name__ == "__main__":
    main()

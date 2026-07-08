"""Omni-anneal (dir #17): unified, config-driven genome + SA over every
per-instance engine-mask class, generalizing anneal_cobind.py (combine only)
and anneal_extract.py (combine+extract).

WHY ONE FRAMEWORK.  Every movable class in #17 is a 1-valu-op <-> 8-scalar-op
equivalence: switching the engine is *arithmetically identical by construction*,
so the only thing that changes is packing/floors -- never correctness. The two
prior scripts each hard-wired one or two classes. This file drives an arbitrary
subset via a CLASS registry, so wiring a class that #15/#18 later exposes
(e.g. rem, gather addr-add, muladd) is one registry entry -- see OMNI_ANNEAL.md.

GENOME.  A JSON-serializable dict {class_name: value}. Mask classes carry a
bool list in per-rotation emit order (True -> valu/1-slot, False -> alu/8-slot);
`offset` carries 32 ints; scalar classes carry one int. Sizes are re-probed from
a fresh build every run (never trusted from a stale champ) -- doc rule #2: after
any op-count change the old numbering mis-indexes, so we re-derive from emit
order and re-seed from the heuristic, not the stale champ.

OBJECTIVE.  realized len(bundles). The scheduler tries all K rotations and keeps
the best; a single pinned rotation (ORACLE_ROT) is a ~0.34s proxy that matches
the full-32 realized on the merged-floor graph. SA optimizes the oracle; new
oracle-bests are confirmed with a full-32 build and (on a genuine full-32 best)
a real machine-vs-reference correctness run before the champ is shipped.

PROPOSAL BIAS (doc rule #1).  Interior engine moves are F-neutral and usually
hurt packing; the wins live in the windup/drain where an engine idles. Mask
flips are therefore sampled with extra weight near the boundaries of emit order,
and each class may carry a mild directional bias (valu->alu vs alu->valu).

Usage:
  cd vliw && python experiments/omni_anneal.py --classes combine,extract,offset
  python experiments/omni_anneal.py --classes combine,extract,offset,xor \
      --iters 20000 --confirm-every 500 --out champ_omni.json
  python experiments/omni_anneal.py --seed-only        # just print seed metrics
"""
import argparse, json, math, os, random, time, sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("PSPACE", "1")
import perf_takehome as P

SHAPE = (10, 2 ** 11 - 1, 256, 16)
FOREST_HEIGHT, ROUNDS, K = 10, 16, 32
ORACLE_ROT = int(os.environ.get("ORACLE_ROT", "29"))
SLOTS = {"valu": 6, "alu": 12, "load": 2, "flow": 1, "store": 2}
DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "..", "champ_omni.json")


# --------------------------------------------------------------------------- #
# Class registry.  Each entry says how to size, seed, and mutate one gene.
# kind:
#   "mask"   -> bool list, len = probe(kb); True=valu(1 slot), False=alu(8).
#   "offset" -> int list, len = 32; per-position emit start offset (clamp >=0).
#   "scalar" -> single int in [lo, hi]; a structural knob (e.g. d3_gather_tail).
# attr    -> KernelBuilder attribute to assign the value to.
# probe   -> (kb) -> size, read AFTER a default build_kernel (re-derived per run).
# seed    -> (kb) -> initial value from the shipped default (rule #2 re-seed).
# flip_bias (mask only) -> P(propose True->False i.e. valu->alu). 0.5 = neutral.
#     The prior scripts used ~0.7 valu->alu because valu is the binding floor
#     post-#12; kept as the default so the framework starts where they left off.
# --------------------------------------------------------------------------- #
class ClassSpec:
    def __init__(self, attr, kind, probe, seed, flip_bias=0.5, lo=0, hi=None):
        self.attr, self.kind = attr, kind
        self.probe, self.seed = probe, seed
        self.flip_bias, self.lo, self.hi = flip_bias, lo, hi


def _default_kb():
    """A fresh build with all defaults -- populates the mask/offset attrs the
    heuristic fills in, which we read back as seeds and to size the genome."""
    kb = P.KernelBuilder()
    kb._rotations = [ORACLE_ROT]
    kb.build_kernel(*SHAPE)
    return kb


def _xor_default_seed(kb, rot=ORACLE_ROT):
    """Materialize the depth>=4 xor rule (perf_takehome.py:646-647) as an
    explicit mask for `rot`. Mirrors the gen_body diagonal loop: exactly one
    `val ^= node` is emitted per _emit_vec_round call, once per valid (diag,q),
    so xor_no order == this loop's order. Verified cycle-identical to the None
    default in the smoke test (build with this seed == build with _xor_mask=None).
    """
    h1 = FOREST_HEIGHT + 1
    pos_off = list(kb._pos_offset)
    perm = [(j - rot) % K for j in range(K)]
    ppos = {perm[p]: p for p in range(K)}
    n_diag = max(pos_off) + ROUNDS
    seed = []
    for diag in range(n_diag):
        for q in range(K):
            j = perm[q]
            r = diag - pos_off[ppos[j]]
            if 0 <= r < ROUNDS:
                seed.append((r % h1) >= 4)
    return seed


CLASSES = {
    "combine": ClassSpec(
        attr="_combine_mask", kind="mask",
        probe=lambda kb: kb._combine_no,
        seed=lambda kb: list(kb._combine_mask),
        flip_bias=0.65),
    "extract": ClassSpec(
        attr="_extract_mask", kind="mask",
        probe=lambda kb: kb._extract_no,
        seed=lambda kb: list(kb._extract_mask),
        flip_bias=0.65),
    "xor": ClassSpec(
        attr="_xor_mask", kind="mask",
        probe=lambda kb: kb._xor_no,
        seed=lambda kb: _xor_default_seed(kb),
        flip_bias=0.5),
    "offset": ClassSpec(
        attr="_pos_offset", kind="offset",
        probe=lambda kb: len(kb._pos_offset),
        seed=lambda kb: list(kb._pos_offset)),
    "d3_gather_tail": ClassSpec(
        attr="_d3_gather_tail", kind="scalar",
        probe=lambda kb: 1,
        seed=lambda kb: int(kb._d3_gather_tail),
        lo=0, hi=8),
    # const->flow rerouting (dir #30): each True flips a distinct non-zero const
    # from the binding load engine to add_imm on the idle flow engine. Sheds one
    # op off the load floor per flip. Co-searched with combine/extract/offset so
    # SA can reorder emit (offset) around the 1-slot flow serialization the
    # isolated #28/#30 tune could not. flip_bias 0.5 (neutral): False->True sheds
    # a load-engine op, True->False returns one -- let SA balance jointly.
    "const_flow": ClassSpec(
        attr="_const_flow_mask", kind="mask",
        probe=lambda kb: kb._const_flow_idx,
        seed=lambda kb: list(kb._const_flow_mask),
        flip_bias=0.5),
    # #47 traverse rem: val%2 == val&1, valu(1 slot) vs alu(8 slots). F-invariant
    # shuffle off the binding valu floor; default all True == shipped `%` on valu.
    "rem": ClassSpec(
        attr="_rem_mask", kind="mask",
        probe=lambda kb: kb._rem_no,
        seed=lambda kb: [True] * kb._rem_no,
        flip_bias=0.7),
}


# --------------------------------------------------------------------------- #
# Build / evaluate
# --------------------------------------------------------------------------- #
def apply_genome(kb, genome):
    for name, val in genome.items():
        spec = CLASSES[name]
        if spec.kind == "mask":
            setattr(kb, spec.attr, [bool(b) for b in val])
        elif spec.kind == "offset":
            setattr(kb, spec.attr, [int(x) for x in val])
        else:  # scalar
            setattr(kb, spec.attr, int(val))


def build(genome, rot=ORACLE_ROT, full=False):
    kb = P.KernelBuilder()
    apply_genome(kb, genome)
    kb._rotations = None if full else [rot]
    kb.build_kernel(*SHAPE)
    return kb


def ev(genome):
    return len(build(genome).instrs)


def ev_joint(genome, rot=ORACLE_ROT):
    """#31 joint-floor score: (realized, joint) on the oracle rotation. joint =
    max(load,alu)+realized so SA is rewarded for closing the load-alu gap even
    before realized moves (a candidate that drops the binding engine's floor
    toward the other scores better at equal realized). Returns (realized, joint,
    load, alu)."""
    kb = build(genome, rot=rot)
    fl = floors(kb)
    realized = fl["realized"]
    joint = max(fl["load"], fl["alu"]) + realized
    return realized, joint, fl["load"], fl["alu"]


def ev_full(genome):
    return len(build(genome, full=True).instrs)


def floors(kb):
    eng = Counter()
    for b in kb.instrs:
        if isinstance(b, dict):
            for e, slots in b.items():
                eng[e] += len(slots)
    valu, alu = eng["valu"], eng["alu"]
    fl = {e: eng[e] / SLOTS[e] for e in ("valu", "alu", "load", "flow", "store")}
    fl["F"] = (8 * valu + alu) / 60.0        # co-bind floor (doc: (8V+A)/60)
    fl["_ops"] = dict(eng)
    realized = len(kb.instrs)
    fl["realized"] = realized
    fl["tail"] = realized - max(fl["valu"], fl["alu"], fl["load"], fl["flow"], fl["F"])
    return fl


# --------------------------------------------------------------------------- #
# Correctness gate (real machine vs reference). Slow (~11s); only run to certify
# a champ we would actually ship. Engine moves are arithmetic-identical by
# construction, but mask/indexing bugs are not -- doc rule: every champ gates.
# --------------------------------------------------------------------------- #
def check_correct(genome):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))
    from frozen_problem import (Machine, build_mem_image, reference_kernel2,
                                Tree, Input, N_CORES)
    forest = Tree.generate(FOREST_HEIGHT)
    inp = Input.generate(forest, 256, ROUNDS)
    mem = build_mem_image(forest, inp)
    kb = build(genome, full=True)
    m = Machine(mem, kb.instrs, kb.debug_info(), n_cores=N_CORES)
    m.enable_pause = m.enable_debug = False
    m.run()
    for ref_mem in reference_kernel2(mem):
        pass
    ivp = ref_mem[6]
    ok = (m.mem[ivp:ivp + len(inp.values)]
          == ref_mem[ivp:ivp + len(inp.values)])
    return ok, m.cycle


# --------------------------------------------------------------------------- #
# Seed + genome sizing
# --------------------------------------------------------------------------- #
def build_seed(active):
    kb = _default_kb()
    sizes, genome = {}, {}
    for name in active:
        spec = CLASSES[name]
        sizes[name] = spec.probe(kb)
        genome[name] = spec.seed(kb)
    return genome, sizes


# --------------------------------------------------------------------------- #
# Neighbor proposals
# --------------------------------------------------------------------------- #
def _boundary_weights(n, head_frac=0.15, tail_frac=0.15, boost=4.0):
    """Weight emit-order indices so flips concentrate in the windup/drain
    (doc rule #1: interior moves are F-neutral and usually hurt packing)."""
    lo, hi = int(n * head_frac), int(n * (1 - tail_frac))
    return [boost if (i < lo or i >= hi) else 1.0 for i in range(n)]


class Proposer:
    def __init__(self, active, sizes, rng, joint=False):
        self.active, self.sizes, self.rng = active, sizes, rng
        self.joint = joint
        self.wts = {n: _boundary_weights(sizes[n])
                    for n in active if CLASSES[n].kind == "mask"}
        # propose a class in proportion to its gene size (bigger -> more moves)
        self.pick_wts = [max(1, sizes[n]) for n in active]
        # #31 joint-floor: the alu-shed partner classes present in the genome.
        self._alu_shed = [n for n in ("combine", "extract") if n in active]

    def _flip_mask_bit(self, mask, name, to_alu=None):
        """Flip one boundary-weighted bit of `mask`; if to_alu given, prefer an
        index currently on that source engine so the flip achieves the intent."""
        # Be robust to temporary size drift between probed sizes and runtime masks.
        # This can happen when new optional knobs alter instrumentation counters.
        wts = self.wts.get(name, [])
        n = min(len(mask), len(wts)) if wts else len(mask)
        if n <= 0:
            return
        mask = mask[:n] + mask[n:]
        if to_alu is None:
            to_alu = self.rng.random() < CLASSES[name].flip_bias
        cands = [i for i, b in enumerate(mask[:n]) if b == to_alu]
        if not cands:
            cands = list(range(n))
        w = [wts[i] if i < len(wts) else 1.0 for i in cands]
        i = self.rng.choices(cands, weights=w, k=1)[0]
        mask[i] = not mask[i]

    def _pick_index(self, name, want=None):
        """Boundary-weighted index; if want in {True,False} restrict to indices
        currently holding the opposite value (so the flip achieves `want`)."""
        w = self.wts[name]
        n = self.sizes[name]
        idxs = range(n)
        return self.rng.choices(list(idxs), weights=w, k=1)[0]

    def mutate(self, genome):
        g = {k: (list(v) if isinstance(v, list) else v) for k, v in genome.items()}
        # #31 joint-floor paired flip: with prob 0.5, if const_flow (load-shed)
        # and a combine/extract (alu-shed) class are both active, propose one flip
        # on each in the SAME step so the walk reaches (load,alu) joint states the
        # one-class-at-a-time mutate cannot. False->True on const_flow sheds a
        # load-floor op; True->False on the alu-shed class returns an alu op to
        # valu (which has ~62 free slots). Arithmetic-identical either way.
        if (self.joint and "const_flow" in self.active and self._alu_shed
                and self.rng.random() < 0.5):
            self._flip_mask_bit(g["const_flow"], "const_flow", to_alu=False)
            an = self.rng.choice(self._alu_shed)
            self._flip_mask_bit(g[an], an, to_alu=True)
            return g
        name = self.rng.choices(self.active, weights=self.pick_wts, k=1)[0]
        spec = CLASSES[name]
        if spec.kind == "mask":
            mask = g[name]
            for _ in range(self.rng.randint(1, 4)):
                self._flip_mask_bit(mask, name)
        elif spec.kind == "offset":
            off = g[name]
            for _ in range(self.rng.randint(1, 2)):
                p = self.rng.randrange(len(off))
                off[p] = max(0, off[p] + self.rng.choice((-1, 1)))
        else:  # scalar
            lo = spec.lo
            hi = spec.hi if spec.hi is not None else lo + 8
            g[name] = min(hi, max(lo, g[name] + self.rng.choice((-1, 1))))
        return g


# --------------------------------------------------------------------------- #
# Champ I/O
# --------------------------------------------------------------------------- #
def save_champ(path, genome, active, oracle, full_cyc, fl, correct):
    payload = {
        "realized": full_cyc,
        "oracle_rot": oracle,
        "oracle_rot_id": ORACLE_ROT,
        "active_classes": list(active),
        "floors": {"valu": round(fl["valu"], 1), "alu": round(fl["alu"], 1),
                   "load": round(fl["load"], 1), "flow": round(fl["flow"], 1),
                   "F": round(fl["F"], 1), "tail": round(fl["tail"], 1)},
        "op_counts": fl["_ops"],
        "genome": {k: ([int(b) for b in v] if CLASSES[k].kind == "mask"
                       else v) for k, v in genome.items()},
        "correct": correct,
    }
    with open(path, "w") as f:
        json.dump(payload, f)


def load_champ(path):
    with open(path) as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
# SA driver
# --------------------------------------------------------------------------- #
def anneal(active, iters, out, seed, confirm_every, T0, cooling, resume,
           joint=False):
    rng = random.Random(seed)
    genome, sizes = build_seed(active)
    if joint:
        if "const_flow" not in active or not any(
                n in active for n in ("combine", "extract")):
            raise SystemExit("--joint-floor requires const_flow AND one of "
                             "combine/extract in --classes")
    if resume and os.path.exists(out):
        d = load_champ(out)
        for name in active:
            if name in d.get("genome", {}):
                val = d["genome"][name]
                if len(val) == sizes.get(name, len(val)) or CLASSES[name].kind != "mask":
                    genome[name] = (list(val) if isinstance(val, list) else val)
        print(f"resumed genome from {out} (sizes checked)", flush=True)

    prop = Proposer(active, sizes, rng, joint=joint)
    if joint:
        cur_r, cur_j, _, _ = ev_joint(genome)
        cur = cur_r
        cur_score = cur_j
    else:
        cur = ev(genome)
        cur_score = cur
    best_oracle = cur
    best_genome = {k: (list(v) if isinstance(v, list) else v)
                   for k, v in genome.items()}
    seed_full = ev_full(genome)
    best_full = seed_full
    print(f"active={active} sizes={sizes} joint={joint}", flush=True)
    print(f"seed: rot{ORACLE_ROT}={cur} FULL32={seed_full}", flush=True)
    fl0 = floors(build(genome, full=True))
    print(f"seed floors: v={fl0['valu']:.1f} a={fl0['alu']:.1f} "
          f"l={fl0['load']:.1f} flow={fl0['flow']:.1f} F={fl0['F']:.1f} "
          f"tail={fl0['tail']:.1f}", flush=True)

    T, t0, accepts = T0, time.time(), 0
    for it in range(iters):
        ng = prop.mutate(genome)
        if joint:
            c, c_score, c_load, c_alu = ev_joint(ng)
        else:
            c = ev(ng)
            c_score = c
        # #31: SA acceptance is over the joint score (gap-closing reward) when
        # --joint-floor is set, but best-tracking + ship gate stay on realized.
        d = c_score - cur_score
        if d <= 0 or rng.random() < math.exp(-d / max(T, 1e-6)):
            genome, cur, cur_score = ng, c, c_score
            accepts += 1
            if c < best_oracle:
                best_oracle = c
                best_genome = {k: (list(v) if isinstance(v, list) else v)
                               for k, v in ng.items()}
                fc = ev_full(best_genome)
                fl = floors(build(best_genome, full=True))
                tag = ""
                if fc < best_full:
                    ok, _ = check_correct(best_genome)
                    if ok:
                        best_full = fc
                        save_champ(out, best_genome, active, best_oracle, fc, fl, True)
                        tag = f"  SHIPPED FULL32={fc} (correct)"
                    else:
                        tag = f"  !! FULL32={fc} but INCORRECT -- not shipped"
                print(f"[it {it} T={T:.2f}] rot={c} FULL32={fc} "
                      f"v={fl['valu']:.1f} a={fl['alu']:.1f} F={fl['F']:.1f} "
                      f"tail={fl['tail']:.1f} ({time.time()-t0:.0f}s){tag}", flush=True)
        T *= cooling
        if confirm_every and it % confirm_every == confirm_every - 1:
            print(f"  it={it} T={T:.3f} cur={cur} best_rot={best_oracle} "
                  f"best_FULL={best_full} acc={accepts/(it+1):.2f} "
                  f"({time.time()-t0:.0f}s)", flush=True)

    print(f"\nBEST rot{ORACLE_ROT}={best_oracle} best_FULL32={best_full}", flush=True)
    if best_full < seed_full:
        print(f"champ shipped to {out} (seed_full={seed_full})", flush=True)
    else:
        print(f"no full-32 improvement over seed ({seed_full}); "
              f"champ not overwritten", flush=True)
    return best_genome, best_oracle, best_full


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--classes", default="combine,extract,offset",
                    help="comma list from: " + ",".join(CLASSES))
    ap.add_argument("--iters", type=int, default=int(os.environ.get("ITERS", "8000")))
    ap.add_argument("--seed", type=int, default=2028)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--confirm-every", type=int, default=500)
    ap.add_argument("--T0", type=float, default=2.5)
    ap.add_argument("--cooling", type=float, default=0.9995)
    ap.add_argument("--resume", action="store_true",
                    help="warm-start genome from --out if class sizes match")
    ap.add_argument("--seed-only", action="store_true",
                    help="print seed metrics + correctness and exit (smoke test)")
    ap.add_argument("--joint-floor", action="store_true",
                    help="#31: score/accept on the joint load+alu objective and "
                         "propose paired const_flow(load-shed)+combine/extract"
                         "(alu-shed) flips; requires those classes in --classes")
    args = ap.parse_args()

    active = [c.strip() for c in args.classes.split(",") if c.strip()]
    for c in active:
        if c not in CLASSES:
            ap.error(f"unknown class {c!r}; choose from {list(CLASSES)}")

    if args.seed_only:
        genome, sizes = build_seed(active)
        o = ev(genome)
        f = ev_full(genome)
        fl = floors(build(genome, full=True))
        ok, cyc = check_correct(genome)
        print(f"active={active} sizes={sizes}")
        print(f"seed rot{ORACLE_ROT}={o} FULL32={f} correct={ok} (machine cyc={cyc})")
        print(f"floors: v={fl['valu']:.1f} a={fl['alu']:.1f} l={fl['load']:.1f} "
              f"flow={fl['flow']:.1f} F={fl['F']:.1f} tail={fl['tail']:.1f}")
        return

    anneal(active, args.iters, args.out, args.seed, args.confirm_every,
           args.T0, args.cooling, args.resume, joint=args.joint_floor)


if __name__ == "__main__":
    main()

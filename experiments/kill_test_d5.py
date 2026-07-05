"""Kill test for direction #21 (d5 partial mux). NO-GO — see
directions/21-d5-partial-mux-NOGO.md.

Op-count model, no perf_takehome edit. Three checks:
  K0  measured baseline floors @1156 (load binding 1070.0)
  K1  §2 mandated sweep on the post-#20 profile: min-over-k not below post-#20
  K2  joint (k4,k5) dominance: the optimum never selects any d5

Run: PYTHONPATH=. python experiments/kill_test_d5.py
"""
import perf_takehome as P
from problem import SLOT_LIMITS, Tree, Input
import collections, random

SLOT = {'load': 2, 'valu': 6, 'alu': 12, 'flow': 1}
# 2-way select op-cost by engine (from #20 §1): flow=1, valu=2 (sub+muladd), alu=16 (2x8 lane)
SEL_COST = {'flow': 1, 'valu': 2, 'alu': 16}


def bind(o):
    f = {e: o[e] / SLOT[e] for e in o}
    k = max(f, key=f.get)
    return k, f[k]


def measured_baseline():
    random.seed(0)
    forest = Tree.generate(10)
    inp = Input.generate(forest, 256, 16)
    kb = P.KernelBuilder()
    kb.build_kernel(forest.height, len(forest.values), len(inp.indices), 16)
    c = collections.Counter()
    for b in kb.instrs:
        for eng, slots in b.items():
            c[eng] += len(slots)
    return {e: c[e] for e in ('load', 'valu', 'alu', 'flow')}, len(kb.instrs)


def best_split_add(o, sel_per_inst, k):
    """Add k mux instances: -8 load each, +sel_per_inst*k selects at optimal engine split."""
    S = sel_per_inst * k
    load_after = o['load'] - 8 * k
    best = None
    for sf in range(0, S + 1):
        rem = S - sf
        for sv in range(0, rem + 1):
            sa = rem - sv
            oo = {'load': load_after,
                  'flow': o['flow'] + sf * SEL_COST['flow'],
                  'valu': o['valu'] + sv * SEL_COST['valu'],
                  'alu': o['alu'] + sa * SEL_COST['alu']}
            m = bind(oo)[1]
            if best is None or m < best[0]:
                best = (m, sf, sv, sa, oo)
    return best


def main():
    base, cycles = measured_baseline()
    print(f"K0  measured baseline @{cycles}:")
    for e in ('load', 'valu', 'alu', 'flow'):
        print(f"      {e:5s} {base[e]:6d} ops / {SLOT[e]:2d} = floor {base[e]/SLOT[e]:7.1f}")
    print(f"      binding: {bind(base)[0]} {bind(base)[1]:.1f}\n")

    # K1: §2 sweep on the post-#20 profile (#20 expected: load 994, flow 780, valu 1050, alu 1060)
    post20 = {'load': 994 * 2, 'flow': 780, 'valu': 1050 * 6, 'alu': 1060 * 12}
    p20 = bind(post20)[1]
    print(f"K1  §2 sweep on post-#20 (binding {p20:.1f}); add d5 = 31 selects/inst:")
    mins = []
    for k in (8, 16, 24, 32):
        m, sf, sv, sa, oo = best_split_add(post20, 31, k)
        mins.append(m)
        print(f"      k={k:2d}: max-floor {m:7.1f} (Δ{m-p20:+6.1f}) load->{oo['load']/2:.0f}")
    print(f"      min over k = {min(mins):.1f}  vs post-#20 {p20:.1f}  ->"
          f" {'KILL (not below)' if min(mins) >= p20 - 0.5 else 'win?'}\n")

    # K2: joint (k4,k5) dominance on the real baseline.
    def eval_state(k4, k5):
        o0 = {'load': base['load'] - 8 * (k4 + k5), 'valu': base['valu'],
              'alu': base['alu'], 'flow': base['flow']}
        S = 15 * k4 + 31 * k5
        best = None
        step = max(1, S // 60)
        for sf in range(0, S + 1, step):
            rem = S - sf
            for sv in range(0, rem + 1, max(1, rem // 60 if rem else 1)):
                sa = rem - sv
                o = {'load': o0['load'], 'flow': o0['flow'] + sf,
                     'valu': o0['valu'] + sv * 2, 'alu': o0['alu'] + sa * 16}
                m = bind(o)[1]
                if best is None or m < best:
                    best = m
        return best

    best4 = min(((k4, eval_state(k4, 0)) for k4 in range(65)), key=lambda t: t[1])
    bestj = min(((k4, k5, eval_state(k4, k5)) for k4 in range(0, 65, 2)
                 for k5 in range(0, 33, 2)), key=lambda t: t[2])
    print(f"K2  best pure-d4: k4={best4[0]} max-floor {best4[1]:.1f}")
    print(f"      global joint optimum: k4={bestj[0]} k5={bestj[1]} max-floor {bestj[2]:.1f}")
    print(f"      -> d5 {'DOMINATED (adds 0)' if bestj[2] >= best4[1] - 0.5 else 'helps?'};"
          f" alu sub-floor {base['alu']/12:.1f} is the real wall.")


if __name__ == '__main__':
    main()

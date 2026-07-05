"""Quantify the 86-cycle tail gap: per-cycle per-engine occupancy of the
shipped schedule, split into setup / windup / steady / drain buckets.

We instrument build_kernel by recording body_start (the setup/body boundary),
then walk kb.instrs computing slot usage per bundle per engine.
"""
import sys
from perf_takehome import KernelBuilder
from problem import SLOT_LIMITS

ENGINES = ["alu", "valu", "load", "store", "flow"]

kb = KernelBuilder()
# monkeypatch to capture body_start: build_kernel appends setup then body.
# We detect the boundary by re-implementing the marker via len tracking.
import perf_takehome as P

orig = P.KernelBuilder.build_kernel
captured = {}
def wrapped(self, *a, **k):
    r = orig(self, *a, **k)
    return r
# Simpler: emit() returns setup start (0). Setup ends where body starts.
# We know setup is everything before the first body bundle. Re-run and find
# body_start via the emit boundary: the setup emit() call is the ONLY emit
# before body. Count setup bundles by re-scheduling setup ops alone is hard;
# instead instrument: patch emit to record its end.
setup_end = {"n": None}
_orig_emit = P.KernelBuilder.emit
def emit_spy(self):
    start = _orig_emit(self)
    setup_end["n"] = len(self.instrs)
    return start
P.KernelBuilder.emit = emit_spy

kb.build_kernel(10, 2047, 256, 16)
instrs = kb.instrs
total = len(instrs)
sstart = setup_end["n"]
print(f"total cycles = {total}")
print(f"setup bundles = {sstart}  |  body bundles = {total - sstart}")

def occ(bundle):
    return {e: len(bundle.get(e, [])) for e in ENGINES}

# op-count totals per engine across body only
body = instrs[sstart:]
setup = instrs[:sstart]

def sum_ops(bundles):
    tot = {e: 0 for e in ENGINES}
    for b in bundles:
        for e in ENGINES:
            tot[e] += len(b.get(e, []))
    return tot

body_ops = sum_ops(body)
setup_ops = sum_ops(setup)
print("\n=== op counts ===")
for e in ENGINES:
    lim = SLOT_LIMITS[e]
    print(f"{e:6s}: setup={setup_ops[e]:5d}  body={body_ops[e]:6d}  "
          f"body_floor={body_ops[e]/lim:8.1f}")

# per-cycle occupancy of body: find windup (ramp to full) and drain (ramp down)
print("\n=== body per-cycle occupancy (first 40 + last 40) ===")
def occ_line(i, b):
    o = occ(b)
    util = f"a{o['alu']:2d}/12 v{o['valu']:1d}/6 l{o['load']}/2 s{o['store']}/2 f{o['flow']}/1"
    # binding: which engines are saturated
    sat = "".join(e[0].upper() for e in ["alu","valu","load"] if o[e]>=SLOT_LIMITS[e])
    return f"cyc {i:4d}: {util}  sat={sat}"

for i in range(min(40, len(body))):
    print(occ_line(i, body[i]))
print("  ...")
for i in range(max(0, len(body)-40), len(body)):
    print(occ_line(i, body[i]))

# Bucket analysis: count cycles where load engine (the binding floor) is NOT full
print("\n=== load-engine idle analysis (load is binding floor 1070.5) ===")
load_full = sum(1 for b in body if len(b.get("load",[]))>=2)
load_part = sum(1 for b in body if len(b.get("load",[]))==1)
load_zero = sum(1 for b in body if len(b.get("load",[]))==0)
print(f"body cycles: load=2:{load_full}  load=1:{load_part}  load=0:{load_zero}")
print(f"total load slots used in body: {body_ops['load']}  (floor {body_ops['load']/2:.1f})")

# where are the load-idle cycles concentrated? first/last 128
first128 = body[:128]; last128 = body[-128:]; mid = body[128:-128]
def load_idle(bs):
    return sum(2 - min(2,len(b.get("load",[]))) for b in bs)
print(f"load-idle slots: windup(first128)={load_idle(first128)}  "
      f"mid={load_idle(mid)}  drain(last128)={load_idle(last128)}")

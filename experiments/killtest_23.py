"""Kill-test for direction #23 mem-bake-k5-barrier.

Measures load- and store-engine idle slots in the windup [0, WIN) of the
current 1156 schedule. The bake needs ~254 vloads + ~254 vstores (gather
subtree tree[15..2046], ~2032 words / 8 = 254 vectors). If load idle slots
in the windup >= 254 (or the combined load+store idle >= what the bake needs
on each engine), the bake can hide for free -> proceed. If load idle < 150 ->
KILL.
"""
import sys
from problem import Tree, Input, build_mem_image, SLOT_LIMITS
from perf_takehome import KernelBuilder

WIN = int(sys.argv[1]) if len(sys.argv) > 1 else 300

f = Tree.generate(10)
inp = Input.generate(f, 256, 16)
mem = build_mem_image(f, inp)
kb = KernelBuilder()
kb.build_kernel(f.height, len(f.values), len(inp.indices), 16)
bundles = kb.instrs
ncyc = len(bundles)
print(f"total cycles = {ncyc}")

load_lim = SLOT_LIMITS["load"]
store_lim = SLOT_LIMITS["store"]

for W in (WIN, min(256, ncyc), min(300, ncyc), ncyc):
    load_used = store_used = 0
    load_busy_cycles = 0
    for b in bundles[:W]:
        lu = len(b.get("load", []))
        su = len(b.get("store", []))
        load_used += lu
        store_used += su
        if lu > 0:
            load_busy_cycles += 1
    load_cap = W * load_lim
    store_cap = W * store_lim
    load_idle = load_cap - load_used
    store_idle = store_cap - store_used
    print(f"\n== window [0,{W}) ==")
    print(f"  load : used={load_used:5d} cap={load_cap:5d} idle={load_idle:5d} "
          f"({100*load_used/load_cap:.1f}% busy, avg {load_used/W:.2f}/cyc)")
    print(f"  store: used={store_used:5d} cap={store_cap:5d} idle={store_idle:5d} "
          f"({100*store_used/store_cap:.1f}% busy, avg {store_used/W:.2f}/cyc)")

# Per-cycle detail for the first WIN cycles: how many cycles have >=1 free load slot
free_load_slots_windup = sum(load_lim - len(b.get("load", [])) for b in bundles[:WIN])
free_store_slots_windup = sum(store_lim - len(b.get("store", [])) for b in bundles[:WIN])
print(f"\nWindup [0,{WIN}): free load slots = {free_load_slots_windup}, "
      f"free store slots = {free_store_slots_windup}")

# Bake requirement estimate
n_nodes = len(f.values)
gather_lo, gather_hi = 15, 2046
gather_words = min(n_nodes, gather_hi + 1) - gather_lo
gather_vecs = (gather_words + 7) // 8
print(f"\nn_nodes={n_nodes}, gather subtree words≈{gather_words}, "
      f"bake needs ≈{gather_vecs} vloads + {gather_vecs} vstores (+ {gather_vecs} valu xors)")
full_vecs = (n_nodes + 7) // 8
print(f"full-tree bake would need ≈{full_vecs} vloads + {full_vecs} vstores")

print(f"\nDECISION: load idle in [0,{WIN}) = {free_load_slots_windup}")
if free_load_slots_windup >= gather_vecs:
    print("  >= bake vloads -> load can hide the bake. Check store too.")
elif free_load_slots_windup < 150:
    print("  < 150 -> KILL per doc §1.")
else:
    print("  150..bake -> partial hiding; net analysis needed.")

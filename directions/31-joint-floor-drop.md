# Direction #31 (E1): joint load+alu floor drop

**Thesis:** load **1064.5** vs alu **1036.7** — gap **28 cycles**. Every historical
attempt drops **one engine** while the other absorbs (Rule A). No one searched
**simultaneous** small cuts on both engines in one graph.

**Mechanism:**
1. Scratch-free load cut (~30 ops, #28-class) AND
2. Structural alu cut (if any remain post-#15) in the **same** build
3. Re-anneal offset/combine/extract on the new op graph

**Implementation:** extend `omni_anneal.py` with optional `joint_probe` mode that
scores `(load_floor, alu_floor, realized)` and proposes paired mask flips only
when both floors move toward each other.

**Unlock:** load < 1036.7 → #27 repack (~61c banked on D4_FREE graph).

**Kill:** if no paired mutation improves realized @1152 after 4k iters → NO-GO.

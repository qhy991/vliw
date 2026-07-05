# Wave-5 — exotic strategies @ 1152

**Baseline:** `explore/merged-floor` @ **1134** cycles after E2 sparse D4_COLD.
**Binding:** load **1043** (PSPACE=0: **1187**).

Wave-4 exhausted scratch-free const moves (#28, #29 NO-GO) and confirmed #26
real implementation NO-GO (pooling penalty > gather-cut prize). Wave-5 targets
**structural oddities** not yet in LESSONS.

| ID | Direction | Doc | Probe |
|---|---|---|---|
| **E3** | Deep vector stagger / windup shrink | `29-deep-stagger.md` | `probe_e3_stagger.py` — **NO-GO @1152** |
| **E1** | Joint load+alu floor drop | `31-joint-floor-drop.md` | (extend `omni_anneal.py`) — **open** |
| **E2** | d4 cold-table via sparse vload mask | `30-d4-cold-vload.md` | `probe_e2_d4_coldmask.py` — **LANDED 1151→1134** (`25,26,27,29,31,34`) |

**Do not retry:** LESSONS §2–§4, Wave-4 A2 (#29 vaddr→flow).

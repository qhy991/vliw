# Direction #29 (E3): deep vector stagger — shrink windup/drain

**Thesis:** Tail gap ~88c is partly structural load-idle in windup/drain (#24).
The shipped `_POS_OFFSET_PSPACE_32x16` beat uniform `p//step` by ~5c at 1208.
At 1152, load binds harder — maybe **more in-flight vectors** (smaller `step`,
or re-searched offsets) fills load slots in cycles 0–47 without touching floors.

**Knobs (correctness-safe):**
- `_step` — block diagonal width (default 4)
- `_key_idx` — scheduler priority key (0..4; S4 says key0 optimal @1156)
- `_pos_offset` — per-position emit start (32 ints); `None` → shipped winner

**Kill criteria:**
- Full-32 rotation best ≤ 1152 with ≥4c gain → land + re-anneal
- All step/key sweeps flat @1152 → NO-GO (windup gap intrinsic @ load-bound)

**Probe result (2026-07-05):** `probe_e3_stagger.py` — **NO-GO**. Shipped
`step=4` + `_POS_OFFSET_PSPACE_32x16` optimal; uniform step=1→1209, step=3→1198.
key_idx 0/2/3 tie @1152; key1→1207, key4→1322. Deeper stagger regresses.

**Probe:** `python experiments/probe_e3_stagger.py`

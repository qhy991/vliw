# Direction: Mem spill for rem history (scratch unlock)

> **Status: PROPOSED** — enables #03 phase-2 when scratch is the blocker (88 words free @ 1208).

## Thesis

#03 phase-2 needs 2–3 `rem` history vectors per lane (+256…768 words). Instead of register
lifetime gymnastics, **spill rem rings to main memory** using the nearly idle store engine
(32 ops / ~2416 slot capacity = 1.3% utilized) and reload in the shallow window before d2/d3
mux rounds.

## Mechanism

- After each traverse: `vstore` `rem` to a dedicated mem region (high addresses in `extra_room`).
- Before depth-2/3 rounds: `vload` rem history vectors.
- Schedule spill/fill in shallow rounds where load engine has headroom (not during gather).

## Risks

- Load engine is saturated on gather rounds — spill/fill must stay in depth 0–1 windows.
- Adds load/store ops; net win only if −320 valu from phase-2 exceeds spill cost.

## Dependency

Land after or in parallel with #12 p-space. Re-sweep mask/offset after landing.

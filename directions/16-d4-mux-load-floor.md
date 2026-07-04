# Direction #16: Depth-4 gather→mux conversion (the only route to load < 1000)

**Thesis:** After #15, the co-bind floor is ~1010 but the **load floor is 1070.5
(2141 ops / 2 slots) — load becomes the binding wall and no valu work matters until it
falls.** The only structural load sink is the deep-round gathers (2048 of 2141 ops).
Depth-4 rounds (r4, r15) touch just **16 distinct nodes (tree[15..30], idx = 15+p,
p∈[0,16))** — convertible from 8 scalar gathers to a 16-way vselect tournament, exactly
like the landed d3 mux. Converting `k` of the 64 depth-4 (vec,round) instances:

| per instance | Δ |
|---|---|
| load  | **−8** |
| flow  | +15 (tournament) |
| valu  | +4 cond extracts (`p&1,2,4,8`) − 1 addr-add = **+3** |

One-time: 2 vloads (tree[15..22], tree[23..30]) + 16 vbroadcasts, shared by both rounds.

- **Priority: 2 (start after #15 lands; independent worktree OK).**
- **Expected at k≈19–23:** load 2141 → ~1957–1989 (**floor 979–995**), flow ≤ 989,
  co-bind F +8–10 (net). Combined with #15: realized **~1050–1070**.
- **Confidence: MEDIUM** — mechanics proven by the landed d3 tournament; the risk is
  scratch (see §3, solvable) and packing.
- **Effort:** 2–4 days (incl. scratch liberation + anneal of `k` and instance choice).

---

## 1. Budget math (why k ≈ 20)

- **Load target:** < 2000 ops → floor < 1000 needs `k ≥ 18`. Every extra conversion
  buys 4 more floor-cycles of headroom.
- **Flow wall:** flow = 704 + 15k must stay < ~990 → `k ≤ 19` bare. The **d1-arith
  rescue** frees 64 more: depth-1 select `node = vselect(p, nb2, nb1)` ≡
  `node = muladd(p, Δ12, nb1)` with `Δ12 = broadcast(tree[2]−tree[1])` (1 valu instead
  of 1 flow, 64 instances) → `k ≤ 23`. Only pay this (+64 valu) if the anneal wants
  k > 19.
- **Which instances:** r4 sits in the load-saturated mid-band — convert r4 instances
  first (relieves the real bottleneck); r15 instances live in the drain where load is
  idler (converting them helps the *floor* but less the *realized*). Make the
  per-instance choice an annealed mask like `_COMBINE_VALU_PSPACE_32x16`
  (`D4_MUX_MASK`, 64 bits), seeded with "all of r4, none of r15".

## 2. Tournament structure (p-space, natural order — mirrors the d3 code)

Conditions are clean bits of `p` (vselect tests ≠0, so raw masks work — no `==1`):
`b0 = p&1, b1 = p&2, b2 = p&4, b3 = p&8` (4 valu `&`; `one/two/four` vectors exist,
add an `eight`). Depth-first evaluation order caps live temps at ~4–5 vectors —
reuse per-vector `node`, `addr` + the mtmp group, or add one `mtmp4_g` per group:

```
L1 (b0): 8 selects over pairs (nb15,nb16)..(nb29,nb30)   # p even → low element
L2 (b1): 4    L3 (b2): 2    L4 (b3): 1  → node           # 15 vselects total
```

Do **not** K5-bake the d4 tables: r3/r14 deferral would pay +1 traverse op in p-space
(the x-format subtract, `perf_takehome.py:658-659`) — exactly net-zero. Leave the defer
set `{0,1,2,10,11,12,13}` alone.

## 3. The scratch battle plan (the real blocker: need 128 words for nb15..nb30)

Current: 1520/1536 used, 16 free. Liberation inventory (all verified against the
PSPACE=1 build):

| source | words | how |
|---|---|---|
| `fvp_p_4` (dead once d4 gathers go) + `fvp_p_5..10` → scalars | **56** | keep 7 *scalar* consts; do remaining gather addr-adds per-lane on alu/flow with the shared scalar (see below) |
| `four` vector (idx-space only, dead under PSPACE=1: `perf_takehome.py:823` emits it unconditionally) | 8 | gate on `not self._pspace` |
| `nn_v` (p-space never wraps; `perf_takehome.py:757`) | 8 | gate |
| `fvp_v` (idx-space gathers only; `perf_takehome.py:756`) | 8 | gate |
| `zero` vector (only user is the d0 p-copy — deleted by #18.1) | 8 | after #18.1 |
| `tree_lo`, `d3_tree_vec` (setup-only after broadcasts consumed) | 16 | reuse as the two d4 table vloads' landing slots or as mtmp4 |
| existing free | 16 | — |
| **total** | **120–136** | need 128 |

Fallback if short: drop `_num_mtmp_groups` 3→2 (−24 words; re-check WAR serialization
cost — it was a tuned knob).

**Addr-add relocation detail:** replacing `v_alu("+", addr, fvp_p_d, p)` for d5..d10
gathers with 8 per-lane ops sharing one scalar const —
`("+", addr+i, idx+i, fvp_p_d_scalar)` on **alu**, or `("add_imm", addr+i, idx+i, imm)`
on **flow** (immediate, zero scratch!) — is F-neutral currency (8 alu ≡ 1 valu in the
co-bind formula) and frees the 56 words. Make the engine choice per-instance and give
it to the #17 anneal.

## 4. Exact change list

1. #18.1 (d0-copy) and the dead-const gating first — they fund the scratch.
2. Setup: 2 vloads at `FVP+15`, `FVP+23`; 16 broadcasts `nb15..nb30`; `eight` const.
3. `_emit_vec_round` depth==4 branch: `if self._d4_mux_mask[self._d4_no]:` tournament
   else `_gather_node` (mirror the d3 `_d3_gather_tail` pattern, including mtmp group
   selection by `j`).
4. Knobs: `D4_MUX_MASK` env/attr (64-bit), default = r4-all/r15-none; `D1_ARITH` bool.
5. Re-anneal offsets + combine mask + `D4_MUX_MASK` jointly (extend
   `experiments/anneal_pspace.py`).

## 5. Verify + kill criteria

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py            # OK, CYCLES < post-#15 number
PSPACE=0 python tests/submission_tests.py   # idx-space path must still pass (gate consts!)
```

- Instrument engine totals: expect load 2141−8k+2, flow 704+15k(−64), valu +3k+16(+64).
- **Kill if:** scratch can't reach 128 free even with the mtmp fallback, or realized
  regresses at every k in {8,12,16,20} after a 2-hour anneal — that would mean the
  mid-band isn't actually load-limited post-#15 (re-measure per-band saturation with
  `watch_trace.py` before concluding).
- **Do not** chase d5 (32-way = 31 flow/instance — flow dies; see 19-moonshots §c).

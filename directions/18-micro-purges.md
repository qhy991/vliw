# Direction #18: Micro purges — certain small deletions (batch, ~−70 valu, −45 load, +100 scratch words)

Small, independently-verifiable deletions. Individually boring; together they fund
#16's scratch budget and shave ~10 floor cycles. Land as one reviewed batch on
`explore/merged-floor` (each item gated by `submission_tests.py`).

## 18.1 `zero` vector dead-code purge (PSPACE=1) — **+8 scratch, −1 setup op**

Trace enumeration (rounds=16, h=10) shows both depth-0 rounds (r=0, r=11) always
enter the defer branch (`perf_takehome.py:650-659` for p-space), so the non-defer
`v_alu("+", idx, c["zero"], addr)` copy at `:662` **never executes** in the
current PSPACE=1 build. The `zero` vector's only other consumer is the wrap
vselect at `:697`, which itself is `not self._pspace`-gated. Net: `zero` is dead
in p-space.

- Wrap `broadcast_const("zero", 0)` (`:754`) in `if not self._pspace:`.
- Optionally leave the dead d0 branch in place (it's cheap and #17 may resurrect
  it as a genome bit — the wash-rounds observation in §18.6).
- *Payoff:* +8 scratch, −1 vbroadcast, and clears one gotcha for the #16
  scratch-inventory count.

**Not −64 valu** (my earlier draft claimed a phantom `+` op — corrected). The
real −64 valu opportunity in this neighborhood is the muladd/`+` collapse at
`:658-659` (d≥1 defer traverse: `muladd(node, idx, 2, one_v)` + `alu(-, idx,
node, addr)` = 2 valu-locked). Skip that: the muladd result is `2p+1` and
subtracting `rem_x` (0 or 1) can't be folded into a single muladd because
muladd's third addend is a full 32-bit vector and `rem_x` isn't a compile-time
constant. Real, but −128 valu at most and structurally messier — deferred to
#17's genome (defer-per-round flag).

## 18.2 Gate idx-space-only consts out of the PSPACE=1 build — **+24 scratch, −6 ops**

`four` (`:823`), `nn_v` (`:757`), `fvp_v` (`:756`) are emitted unconditionally but only
read by idx-space paths (d2 idx-mux, wrap, idx-gather). Wrap in
`if not self._pspace:`. Zero risk; `PSPACE=0 python tests/submission_tests.py` guards
the fallback.

## 18.3 `fvp_p_d` broadcast vectors → scalar consts — **+56 scratch** (F-neutral)

`:764-767` burns 8 words per depth constant just so one `v_alu("+")` can read it.
Emit per-lane adds against a *shared scalar* const (8 alu: `("+", addr+i, idx+i, fvp_p_d_s)`)
or 8 flow `add_imm` (immediate — no scratch at all). This is co-bind currency (1 valu
↔ 8 alu), so hand the per-instance engine choice to #17; the point here is the 56
words for #16's tables. Keep `fvp_p_3` only if `D3_GATHER_TAIL > 0`.

## 18.4 `vaddr` consts → flow `add_imm` — **−31 load ops (−15.5 load floor)**

`:917`: 31 per-vector `vaddr` constants are emitted as `const` ops on the **load**
engine. They're `IVP + j*8` — computable as `add_imm(vaddr_j, ivp_scalar, j*8)` on
flow (idle in setup) or alu. Load floor is the wall post-#15, so −31 load ops is a
real half-point. Same trick for any other setup `const` that a flow `add_imm` off an
existing scalar can produce (audit `scratch_const` call sites; header consts
`n_nodes/FVP/IIP/IVP` are 1 `vload` of `mem[0..7]` + lane reads if needed).

## 18.5 Setup-vector reuse — **+16 scratch**

`tree_lo` (`:794`) and `d3_tree_vec` (`:857`) are dead after the setup broadcasts.
Reuse their 16 words as #16's d4 vload landing slots or as an extra mtmp group.
(Bump-allocator: just pass the addresses, no allocator change needed.)

## 18.6 Defer-set re-audit (p-space) — **±0 now, unlocks clarity**

In p-space, deferral on d≥1-traverse rounds costs +1 op (`:658-659` muladd+sub vs one
muladd), exactly cancelling the s5 saving on r1/r2/r12/r13. The current 7-round set is
therefore equivalent to `{0,10,11}` + 4 no-ops. Two actionable corollaries:
(a) don't extend deferral anywhere new (e.g. into mux-converted d4 — see #16 §2);
(b) the 4 wash-rounds give #17 two *different* op shapes with identical cost — an
extra packing degree of freedom (defer flag per round into the genome).

## Verify (whole batch)

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py            # OK, CYCLES <= previous
PSPACE=0 python tests/submission_tests.py   # 18.2/18.3 must not break idx-space
# scratch: assert self.scratch_ptr report shows >= 128 free before #16 starts
```

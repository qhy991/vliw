# Direction: p-space traversal — maintain parity `p` instead of full `idx`

> **Status: ACTIVE — highest priority on 1208 base.** Attempted on merged-floor (July 2026);
> first implementation failed correctness (K5-deferral × d2/d3 borrow mixing). Do not ship
> until `submission_tests.py` passes. This doc captures the intended design.

## 1. Thesis

The verified invariant (`parity_check.py`, 0/4096 violations):

```
idx == 2^d − 1 + p
```

where `p` is the parity accumulator updated each traverse. Since `idx` is an affine function
of `p`, **store `p` in the scratch slot that currently holds `idx`** and stop materializing
the full index on non-gather rounds.

## 2. Op-count win

**Traverse** (non-defer, depth ≥ 1): today `i2p1 = 2*idx+1` (muladd) + `idx = i2p1+rem`
(add) → 2 valu. p-space: `p ← 2*p + rem` — **one `multiply_add`** (rem vector is already in
`addr`; ISA `multiply_add` takes three vector addresses, `problem.py` confirmed).

**Rounds affected:** non-defer deep rounds `{3..9, 14}` × 32 vectors = **256 valu ops**
deleted. K5-deferral rounds keep parity-flip semantics (2 ops); net **−256 valu**, **zero
scratch**.

**Gather address:** `addr = fvp + idx = (fvp + 2^d − 1) + p`. Fold `fvp + 2^d − 1` into a
per-depth setup broadcast (`fvp_p_4` … `fvp_p_10`, 7 vectors = 56 words scratch — fits in
88 words free @ 1208). depth-3 gather tail: two adds `fvp_v + p + 7`.

**Wrap:** round-10 idx update already deleted (#11); round-11 depth-0 sets `p = rem`
(fresh). No wrap cost in p-space.

**depth-1:** `vselect(node, p, …)` — cleaner than borrowing `addr` lifetime for `rem_{r-1}`.

## 3. Interaction with #03 phase-2

p-space and d2/d3 parity-carry are **orthogonal**:

- p-space: deletes **traverse** `i2p1+add` on deep rounds.
- #03 phase-2: deletes **mux** `&`-extracts via re-permuted `tree[2^d−1+p]` tables.

**Do not** extract mux bits as `p>>k` — idx low bits are borrow-mixed (`¬(p&1)` at d2, etc.).
Either materialize `idx_true = (2^d−1)+p` before mux (+1 valu per shallow round) or complete
phase-2 table re-permute keyed on raw `rem` vectors.

## 4. K5-deferral traverse rules

| case | p update |
|---|---|
| defer, depth 0 | `p = 1 − rem_x` (not `2 − rem_x`; that is full `idx`) |
| defer, depth ≥ 1 | `p = 2*p + rem_true`, `rem_true = rem_x ^ 1` |
| non-defer, depth 0 | `p = rem` |
| non-defer, depth ≥ 1 | `p = 2*p + rem` |

`enter_x` / K5-baked broadcasts unchanged — only affects `val^node`, not `p` algebra.

## 5. Floor impact

−256 valu → valu floor 1111.3 → **~1068**. Combined floor with alu rebalancing target
**~1077** (move ~34 combines from alu tail back to valu via mask re-sweep).

Realized (with ~8.7% tail inflation): **optimistic 1150–1180** if mask/offset re-sweep
succeeds; may stay ~1200 if inflation absorbs the drop.

## 6. Day-1 experiment

1. `PSPACE=1` flag in `KernelBuilder`; default off on 1208 branch.
2. Correctness: `parity_check.py`, `algebra_check_ported.py`, `submission_tests.py`.
3. Cycles + engine histogram vs 1208 base.
4. Coordinate-descent on `COMBINE_HEAD/TAIL` after p-space lands.

## 7. Known failure mode (July 2026 attempt)

Naïve `p>>1` / `p>>2` for d2/d3 mux conditions → ~50% lanes wrong (borrow mixing).
Naïve `p = 2 − rem_x` at defer depth-0 → wrong `p` at depth-1 entry. Scratch overflow if
all `fvp_p_3..10` allocated — use `fvp_p_4..10` only + two-add path for d3 gather.

# Direction #36 — O3 axis: alu computation elimination (b0-carry)

Wave-6 orthogonal axis O3 (see `35-orthogonal-axes.md`). Goal: **reduce the alu
op TOTAL** (lower the alu floor) without raising another engine — a stackable
lever for after O1 drops load below the alu wall.

## Baseline alu composition @ 1111 (measured, oracle rot, single build)

```
alu 12440 ops / 12 = 1036.7  (SUB-floor; load 1083.5 BINDS by 47c)
  combine-XOR (^)  10032 ops  836c   <- hash stages s1/s3/s5 combines
  val^node   (^)    2048 ops  170c   <- per-round tree-node mix
  extract    (&)    1936 ops  161c   <- idx&1 / p&1 bit extracts (b0/b1/b2)
  extract    (<)     472 ops   39c   <- hi = (1<p)
```
5-engine floor @1111: load **1083.5** BIND, alu 1036.7, F 1028.9, valu 1027,
flow 743, tail 27.5.

## LANDED (gated, default OFF): b0-carry extract elimination — `B0_CARRY=1`

**Identity (proven 200k random + structural):** the low bit `b0 = idx&1` at a
depth-2/3 mux round is NOT a fresh computation. In p-space `p_next = 2·p_prev +
rem`, so `b0(p_cur) == rem` of the *immediately preceding* round's traverse.
Every depth-2/3 round is `enter_x` (its predecessor always defers `^K5`), so that
predecessor's deferred traverse left `rem_x = rem_true ^ 1` in the **per-vector
`addr` register**, and nothing overwrites `addr` before the node-select. Since
`rem_x == b0 ^ 1`, drop the `&` extract and key the b0-vselects on the live
`addr` with **swapped branch args**. (`K5 & 1 == 1`, so `rem_x = rem_true ^ 1`.)

- **Scratch-free** — reuses the live `addr` reg. This is the crucial difference
  from the killed **#22** (traverse phase-2 purge), which needed a 3-vector
  `rem`-ring = +256..768 words and died on the scratch budget (21 free here).
  b0's carry is only **1 round deep** → already in a register, zero scratch.
- **alu-only elimination (orthogonal):** removes 128+128 `&` vec-instances
  (−2048 alu ops). No engine rises — valu also drops slightly, load/flow flat.
- p-space only (`self._pspace` guarded); PSPACE=0 restores the baseline path
  (1180, unchanged). Correctness: parity 0, submission machine-vs-ref bit-exact
  at PSPACE=1 (1118) and PSPACE=0 (1180).

### 5-engine floor before → after (full-32 realized)

| build | realized | load | alu | valu | flow | F |
|---|---:|---:|---:|---:|---:|---:|
| base | 1111 | 1083.5 | **1036.7** | 1027 | 743 | 1028.9 |
| +b0carry | 1118 | 1083.5 | **972.0** | 1024 | 743 | 1013.3 |
| D4FREE base (alu binds) | 1102 | 87.5 | 1036.7 | 1027 | 743 | 1028.9 |
| D4FREE +b0carry | **1073** | 87.5 | **972.0** | 1024 | 743 | 1013.3 |

**Orthogonality contract: PASS.** alu −64.7c, F −15.6c, valu −3c; nothing rises.
It is an *elimination* (redundant recompute removed), not a shuffle.

### Why it REGRESSES on the 1111 graph (default OFF)

alu is a **47c sub-floor**; load binds. Worse, the extracts double as
**tail-packing filler** — removing them for free raises realized +7c (1111→1118),
exactly as the zero-cost ceiling probe predicts (skip-all-&-extracts → 1130).
So b0-carry cannot pass `CYCLES<1111` **alone** on this graph. It is a
**stackable** lever: it only pays once O1 (load-cut) makes alu the wall.

### Stacking ceiling (honest)

realized ≥ max(load, alu, valu, F). After b0-carry the next wall is **valu 1024**
(barely touched by O3). So b0-carry's stackable gain is **capped at ~12.7c**
(load-cut graph: 1102→1073 is −29c because tail also repacks; pure-floor cap vs
valu is 1036.7→1024 = 12.7c). Below 1024 needs O2 (valu fusion). For sub-1000
the three axes must genuinely stack: **O1 load + O3 alu/F + O2 valu**.

## NO-GO within O3

- **hash-XOR combines (836c, the alu bulk) — irreducible.** s1 = `(v^K1)^(v>>19)`
  and s5 = `(v^K5)^(v>>16)` are bijective xorshift folds with full 32-bit
  liveness (sampled: 0 collisions, 0 dead input bits) — matches killed **#19a**.
  s2+s3 `t1^t2` is already the fused form (#15). The `^` cannot be *eliminated*,
  only moved to valu — a **shuffle** (raises valu/F), forbidden by the contract.
- **`hi = (1<p)` extract (39c) — no scratch-free carry.** `hi(p_cur)` truth is
  NOT `bit1(p_cur)` for p≥4 (depth-3 range), and `podd_prev` (which would give
  it) is overwritten each round — carrying it needs a dedicated per-vector reg
  (scratch) we don't have. Recompute stays.
- **`val^node` per-round mix (170c) — fundamental** (tree-node hashing input).

## Reproduce
```bash
# lever (gated): PSPACE=1 -> 1118 (alu 972), PSPACE=0 -> 1180 (guard->baseline)
B0_CARRY=1 python tests/submission_tests.py
B0_CARRY=1 python parity_check.py
# floors + ceiling probe: see git history of this branch / probe snippets in commit msg
```

## Resurrection / integration
b0-carry is **ready to stack**: enable `B0_CARRY=1` in the final O1+O2+O3 env
A/B once O1 has pushed load below ~1024. It composes as a clean disjoint hunk
(depth-2/3 blocks in `_emit_vec_round`, one `__init__` flag). Do not ship default-on
until load < alu (else +7c regression).

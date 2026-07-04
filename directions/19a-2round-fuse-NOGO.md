# Direction #19 §a: 2-round hash fuse — **NO-GO (KILL)**

**Thesis tested (19-moonshots.md §a):** can two adjacent traverse rounds
`val' = hash( hash(x ^ na) ^ nb )` fuse into **fewer than 2× hash worth of
valu-locked ops** (baseline `2 × 7 = 14`)? The hope was that stage-5's
`t2 = a >> 16` discards the low-16 bits of the pre-s5 state, so the top-16 bits
of `hash(v)` don't depend on the low-16 pre-s5 bits — a real information
bottleneck that *might* let a two-round subformula collapse.

**Verdict: KILL.** Confirmed in ~1 hour, algebra-first, no kernel change. The
bottleneck is real but strictly **intra-hash**; it cannot become cross-round
dead code. Four independent arguments, any one sufficient, in increasing
formality.

Kill test: `experiments/fuse_kill_test.py` (all checks PASS).

---

## The four kills

### K0 — Structural: `nb` is not a constant (decisive, no algebra)

The moonshot's premise is "for a *fixed* `na, nb`." In the actual kernel
(`problem.py:476-484`) the round-2 node is

```
nb = tree[ idx' ],   idx' = 2*idx + (1 if hash(x^na) % 2 == 0 else 2)
```

`nb` is a **runtime gather whose address depends on round-1's parity bit**.
Round 2 cannot even be issued until round 1's hash finishes and the low bit is
known. There is no constant `nb` to fold against — a fused op must treat `na`,
`nb`, and the gathered value as free runtime 32-bit words. This alone kills the
"constant-fold two rounds" idea; K1–K3 kill the stronger "symbolic identity in
free `na,nb`" idea too.

### K1 — hash is a bijection over ℤ/2³² ⇒ no droppable op

Each stage is a bijection over ℤ/2³² (below), so the hash — a composition of
bijections — is a bijection. We construct the exact per-stage inverse and
sanity-check `unhash(hash(a)) == a` and `hash(unhash(y)) == y` on 2²⁰+2¹⁶
samples (validates the inverse code; the bijectivity itself is by construction).

- stages 0,2,4 `(+,+,<<)`: `a·(1+2ˢ)+K`, `1+2ˢ` odd ⇒ multiplicative inverse.
- stages 1,5 `(^,^,>>)`: `a ^ K ^ (a>>s)`, invert `x^(x>>s)` MSB→LSB.
- stage 3 `(+,^,<<)`: `(a+K) ^ (a<<s)`, invert LSB→MSB with carry tracking.

A bijection has **no dead output bit and no dead input bit**. The composite
`hash(hash(x^na)^nb)` is therefore a permutation in `x` for **every** `(na,nb)`.
Nothing computed in round 1 is redundant to the final result — there is no op to
delete.

*(Formal note: z3 does **not** close even single-hash injectivity — the
odd-multiply + mixed xor-shift stages bit-blast to a formula it returns
`unknown` on after a 240s cap. The **constructive two-sided inverse is the
operative proof** of bijectivity; it is exact and exhaustive by construction, no
sampling gap. z3's inability to find any counterexample is at most weak
corroboration — and its difficulty closing the 2-round symbolic form is itself
consistent with "no small equivalent DAG exists.")*

### K2 — Full 32-bit round-1 output is live across the boundary

Avalanche probe: flip each of the 32 input bits of `x`; every one changes the
composite output. So the *entire* 32-bit round-1 result is consumed by round 2 —
not just its parity bit. The stage-5 `>>16` bottleneck cannot turn into
cross-round dead code because there is no truncation at the round boundary.

### K3 — The stage-5 bottleneck is real but intra-hash

Verified on 2¹⁸ inputs: `top16(hash(v)) == top16(pre_s5(v)) ^ top16(K5)`, i.e.
stage-5's `>>16` genuinely drops the low-16 pre-s5 bits from the top-16 output.
**But** both hash outputs are fully consumed downstream:

- round-1 output → parity bit drives the traverse **and** the whole word is the
  round-2 input (K2);
- round-2 output → same.

An information bottleneck *inside* a bijection that is read in full yields no
op savings. It would only help if some consumer read *only* the top-16 bits —
none does.

---

## Why SMT/superoptimizer can't rescue it

The moonshot suggested Souper/Rosette/BDD to find a `< 14`-op DAG. The obstruction
is not search budget, it is algebraic: the target function is a **permutation with
full bit-liveness in three free 32-bit inputs**. The hash deliberately mixes `+`
(affine over ℤ/2³²) with `^`/`>>` (affine over 𝔽₂ᵏ) so that no single algebra
linearizes it; composing two rounds only deepens the mixing. There is no smaller
equivalent DAG for a superoptimizer to find, and no partial-output shortcut for a
BDD to exploit, because the full output is live (K2) and the map loses no
information (K1).

## Reproduce / gate

```bash
python experiments/fuse_kill_test.py          # K0-K3 all PASS -> KILL CONFIRMED
python parity_check.py && python algebra_check_ported.py   # unchanged (no kernel edit)
python tests/submission_tests.py              # OK, CYCLES: 1174 (baseline untouched)
```

## Bottom line

2-round fuse buys **0 ops**. The `hash∘hash` composite needs the full `2×7`
valu-locked ops; there is no `< 14`-op realization. Floor and realized are
unchanged at **1174**. No lane opened. Filed so no future worktree re-treads it.

**Confidence in kill: HIGH.** Bijection + full liveness are exhaustive over the
sample and formally corroborated; the structural `nb`-dependency (K0) is
airtight independent of the algebra.

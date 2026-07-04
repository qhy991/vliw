# Direction #15: Stage-2+3 muladd fusion (resurrect the "R1 trap" — the regime flipped)

**Thesis:** Fuse hash stages 2 and 3 into `2 muladd + 1 combine`, deleting **1 valu op
per (vec, round) = −512 valu ops**. This is exactly the transform that
`02-hash-opcount.md §5 R1` declared "proven dead, do NOT chase" — but that verdict was
priced in the **1230-era regime where ALU was the binding engine**. Since #12/#14 the
binding flipped to **valu** (6595 ops, floor 1099 vs alu 994.7). In a valu-bound regime,
deleting a valu-locked op is a pure floor win. **This is the single largest verified
op-count lever left on the board.**

- **Priority: 1 (do this first, before anything else).**
- **Expected:** co-bind floor 1078.3 → **1010.0** (−68). Realized 1179 → **~1105–1125**
  after re-anneal.
- **Confidence: HIGH** — algebra verified bit-exact against `myhash` on 500k random
  inputs + edge cases (see §4). Same shape as the landed muladd fusions.
- **Effort:** ~0.5–1 day including the mandatory re-anneal.

---

## 1. The algebra (verified exact, mod 2^32)

Current emission (`perf_takehome.py:625-627`):

```python
self.v_muladd(val, val, c["m33"], c["K2"])                            # s2: u = a*33 + K2
self.v_alu("+", node, val, c["K3"]); self.v_alu("<<", addr, val, c["sh9"])  # s3: t1, t2
self._combine(val, node, addr)                                        # s3: u' = t1 ^ t2
```

4 ops (3 valu-locked + 1 movable combine). Stage 3 is `(u + K3) ^ (u << 9)` where
`u = a*33 + K2` and `a` is the stage-1 output. Both stage-3 operands are **affine in
`a`**, so each is one muladd *from `a` directly*:

```
t1 = u + K3    = a*33    + (K2 + K3)         (fold K3 into stage-2's addend)
t2 = u << 9    = (a*33 + K2) * 512
               = a*16896 + (K2 << 9)         (shift distributes over muladd)
```

New emission — replaces all three valu-locked ops with two, **same dest registers, same
combine, no liveness change**:

```python
self.v_muladd(node, val, c["m33"],    c["K2K3"])   # t1 = a*33    + 0xE9F8CC1D
self.v_muladd(addr, val, c["m16896"], c["K2S9"])   # t2 = a*16896 + 0xACCF6200
self._combine(val, node, addr)                     # stage-3 out = t1 ^ t2
```

Verified constants (from `HASH_STAGES`, K2=0x165667B1, K3=0xD3A2646C):

| const | value | replaces |
|---|---|---|
| `K2K3`   | `0xE9F8CC1D` = (K2+K3) mod 2^32 | `K2` vector (reuse slot) |
| `m16896` | `0x4200` = 33·512 | `sh9` vector (reuse slot) |
| `K2S9`   | `0xACCF6200` = (K2<<9) mod 2^32 | `K3` vector (reuse slot) |

**Net scratch: 0** (three consts die, three are born). `m33` is still used by t1.

Bonus ILP: today s3 waits on the s2 write of `val`; after fusion both muladds read the
*stage-1* output in parallel — the critical path through the hash shrinks by one level
per round, which helps exactly where the drain hurts.

## 2. Why R1's "net loss" verdict is stale

R1's accounting: the fusion "converts one flexible op into a second valu-locked muladd"
— true, and fatal **when alu was binding** (1230 era: alu floor 1195 > valu 1169, so
flexibility was the scarce resource). Post-#12/#14 the co-bind optimum is
`F = (8·valu + alu)/60` (derivation in `PLAN-1000.md §2`): each *deleted* valu op is
worth 8/60 cycle regardless of flexibility, and the movable-combine pool (1536
instances) vastly exceeds the ~23 migrations the new equilibrium wants. Fusion delta:
valu −512, alu 0, movable combines unchanged (still 3/hash):

```
F_now  = (8·6595 + 11936)/60 = 1078.3
F_new  = (8·6083 + 11936)/60 = 1010.0      (valu-only floor 6083/6 = 1013.8)
```

After this lands, **amend `02-hash-opcount.md` R1** with a pointer here so nobody
re-kills it on sight.

## 3. Exact change list

1. `perf_takehome.py:748` region — replace the `K2`/`K3`/`sh9` broadcast consts with
   `K2K3`, `m16896`, `K2S9` (values above; keep `m33`).
2. `perf_takehome.py:625-627` — the 3-line swap from §1.
3. Nothing else changes: stages 0/1/4/5, K5-deferral, traverse, masks, offsets are all
   untouched. The combine count and numbering (`_combine_no`) are unchanged, so
   `champ_cobind.json` / `_COMBINE_VALU_PSPACE_32x16` still index the same instances.
4. Re-anneal (mandatory, the mask/offsets were tuned for the old op graph):
   `experiments/anneal_cobind.py` then `experiments/anneal_pspace.py` style joint
   offset+combine search. Expect the optimizer to move ~30–80 combines valu→alu
   (equilibrium m* ≈ 23 from `PLAN-1000.md` math; the SA will find the discrete best).

## 4. Verification gates (in order)

```bash
# 1. standalone algebra check (already passed 2026-07-04, keep as regression):
python3 - <<'EOF'
import random
from problem import HASH_STAGES, myhash
M = 2**32; K2 = HASH_STAGES[2][1]; K3 = HASH_STAGES[3][1]
K2K3, M16896, K2S9 = (K2+K3)%M, 33*512, (K2<<9)%M
def fused(a):
    a = ((a + HASH_STAGES[0][1])%M + (a<<12)%M)%M
    a = ((a ^ HASH_STAGES[1][1]) ^ (a>>19))%M
    a = ((a*33 + K2K3)%M) ^ ((a*M16896 + K2S9)%M)
    a = ((a + HASH_STAGES[4][1])%M + (a<<3)%M)%M
    return ((a ^ HASH_STAGES[5][1]) ^ (a>>16))%M
random.seed(42)
assert all(fused(a)==myhash(a) for a in (random.randrange(M) for _ in range(500000)))
print("OK")
EOF
# 2. invariants:  python parity_check.py && python algebra_check_ported.py
# 3. correctness+score:  python tests/submission_tests.py     # OK, CYCLES <= 1179
# 4. fallback path:      PSPACE=0 python tests/submission_tests.py
```

## 5. Risks / kill criteria

- **R1 (low):** combine-mask indices shift if any other emission change sneaks in —
  land this *alone* on a clean branch. If `submission_tests` fails, diff the value
  trace at `hash_stage 2/3` (debug `vcompare` hooks exist in `problem.py`).
- **R2 (low):** realized gain lags the −68 floor drop until the re-anneal runs; do not
  judge the direction on the pre-anneal number.
- **Kill if:** valu op count doesn't drop by 512±16 (instrument the op list), or
  post-anneal realized > 1140 — then the tail gap grew pathologically and #17's
  boundary work moves up in priority.

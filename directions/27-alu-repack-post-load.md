# Direction #27: alu repack after load floor drop

**Baseline:** **1156** standalone; designed for post-**#26** graph (~1088, alu binds).

**Thesis:** D4_FREE shows after load cut, **alu 1036.7** becomes binding. Move
engine-neutral ops (combines, xor, addr-add, extracts) **alu→valu** where valu
has slack, without re-raising load.

- **Priority: 3** — meaningful only after #26 lands OR on D4_FREE probe schedule.
- **Confidence: MEDIUM** — mirror of #14/#15a but direction reversed (alu→valu).
- **Effort: 1–2 days.**

## 1. Method

1. On D4_FREE probe or #26 landed build, dump engine totals per band.
2. Extend `omni_anneal.py` if needed: bias proposals **alu→valu** (inverse of #14).
3. Target: close gap between realized and max(alu, load) to ≤40 cycles.
4. Promote champ to `perf_takehome.py` constants only after full-32 + correctness gate.

## 2. Kill criteria @ 1156 (no #26)

If run on 1156 without load drop: expect **NO-GO** (alu already sub-floor). Document
and stop — do not burn iterations.

## 3. Verify

```bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py   # beat post-#26 number, not just 1156
```

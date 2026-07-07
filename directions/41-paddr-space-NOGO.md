# PADDR-Space Deep Gather Address Carry — NO-GO

Baseline: **1092 cycles** on `explore/w7-optimize`.

## Hypothesis

Carry deep-gather memory addresses directly for depths 5-10 so the next gather
does not need `addr = fvp_p_d + p` on its critical path.

Depth 4 was deliberately left in normal p-space because the shipped sparse
`D4_COLD_MASK` consumes raw `p` bits. The prototype converted the depth-4
traverse into a depth-5 address and then maintained address-space recurrence for
depths 5-10:

```text
paddr_d      = FVP + 2^d - 1 + p
paddr_next   = 2 * paddr_d + rem + (1 - FVP)
```

This is algebraically equivalent for non-defer deep rounds and was tested through
the normal submission harness.

## Result

```text
baseline:
  python tests/submission_tests.py
  OK, CYCLES: 1092

prototype:
  PADDR_SPACE=1 python tests/submission_tests.py
  OK, CYCLES: 1094

prototype profile:
  cycles 1094
  scratch 1479 free 57
  ops {'load': 2067, 'flow': 859, 'valu': 6289, 'alu': 11160, 'store': 32}
  load_ops {'const': 47, 'vload': 36, 'load': 1984}
  floors {'load': 1033.5, 'alu': 930.0, 'valu': 1048.1666666666667,
          'flow': 859.0, 'store': 16.0}
  F 1024.5333333333333
```

## Verdict

**NO-GO.** The prototype is bit-exact but regresses 1092 -> 1094.

It removes four setup const loads and four valu setup ops and frees 36 scratch
words, but the address add is moved rather than deleted. The paddr-bias
dependency does not shorten the drain critical path enough to offset the
schedule disruption, and the binding walls remain effectively unchanged:

```text
baseline:  load 1035.5, valu 1048.8, F 1025.1
prototype: load 1033.5, valu 1048.2, F 1024.5
```

This confirms that the current 1092 graph is not losing primarily on the
per-depth gather address add. Future sub-1000 work still needs either fewer real
deep gathers or a shorter hash/traverse critical path.

## Free-Address Lower Bound

After killing the correctness-preserving prototype, I also ran a wrong-output
lower-bound probe that made p-space gather address calculation free by depth.
This isolates the maximum possible scheduling value of deleting those adds:

```text
free_addr [4] cycles 1101
free_addr [5] cycles 1103
free_addr [6] cycles 1099
free_addr [7] cycles 1101
free_addr [8] cycles 1102
free_addr [9] cycles 1094
free_addr [10] cycles 1097
free_addr [5, 6, 7, 8, 9, 10] cycles 1097
free_addr [4, 5, 6, 7, 8, 9, 10] cycles 1096
```

Even the impossible "all depth4-10 address adds are free" bound does not beat
1092. That rules out more elaborate correct encodings whose only payoff is
removing or moving `addr = fvp_p_d + p`.

## Reproduce

The prototype was intentionally removed from `perf_takehome.py` after the kill.
To reproduce, re-apply a default-off `PADDR_SPACE` patch that:

- carries address-space state only for depths 5-10,
- keeps depth 4 in p-space for `D4_COLD_MASK`,
- uses `paddr_next = 2*paddr + rem + (1-FVP)` for deep non-defer traversal,
- skips `fvp_p_6..fvp_p_10` setup broadcasts.

Then run:

```bash
PADDR_SPACE=1 python tests/submission_tests.py
```

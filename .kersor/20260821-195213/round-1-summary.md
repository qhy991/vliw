# Run 1 Result — `vliw-bundling-kernel-optimization`

## Outcome

| Metric | Value |
|---|---|
| Measured cycles | **2235** (baseline 147734) |
| Speedup | **66.10x** |
| Correctness | 8/8 trials PASS (`CorrectnessTests.test_kernel_correctness`, pinned python 3.14.6) |
| Workflow run | wf_0ab99296-8ed (4 agents, 0 errors, resumed after 429 reset) |

## Lineage

- kersor-11 same-task protocol result: 69.36x @ 2130 cycles
- this session: 66.10x @ 2235 cycles (95% of kersor-11, same strategy class)
- theoretical floor for the gather+valu strategy class: ~72x

## Host review amendments (3 seam fixes, all in run-1/host-verification.json)

1. `alloc_vreg` alias — part 1 named it `alloc_scratch`, part 3 called `alloc_vreg`
2. `rw()` generic valu branch tracked only `vec(s[2])` reads; added `vec(s[3])`
3. **Init/const slots were never packed** — `build()` was called on `body` only,
   silently dropping every `emit()`'d init slot (header loads, consts, broadcasts);
   fixed by packing `self.slots + body` in one program-order pass

## Notes

- The 429 rate-cap killed generate-part-2 mid-run (window reset 12:08:48);
  resume replayed analyze + part-1 from cache and ran parts 2-3 live.
- Chunked Generate (3 x <=120 lines) fully solved the 32k output-cap failure
  that aborted all three kersor-11 author agents.

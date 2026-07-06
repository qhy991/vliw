# Test Method — VLIW perf_takehome @ 1134

## Environment
- Conda env: `vllm`
- Working directory: `/mnt/user_dir/shihaichao/qinhaiyan/vliw`
- Default env: `PSPACE=1`

## Correctness
```bash
source /mnt/user_dir/shihaichao/qinhaiyan/miniconda3/etc/profile.d/conda.sh && conda activate vllm
cd /mnt/user_dir/shihaichao/qinhaiyan/vliw
python parity_check.py && python algebra_check_ported.py
```
- Pass: parity 0 violations; algebra ALL-PASS

## Benchmark (primary metric)
```bash
python tests/submission_tests.py
```
- Pass: prints `OK`, `CYCLES: N` where N <= current best (1120)
- Also run: `PSPACE=0 python tests/submission_tests.py` (must not regress 1187)

## Baseline
- Baseline Latency (ms): 1120
- Baseline: merged-floor-1120
- Baseline Detail: merged-floor @ 1134 cycles (130.28× over 147734 reference)
- Timing Method: e2e
- Baseline Status: present

## Local optimization tools (USE THESE — not CUDA workflows)
| Tool | Purpose |
|------|---------|
| `experiments/omni_anneal.py` | Joint SA: combine/extract/offset (re-seed after op-count changes) |
| `experiments/kersor_vliw_round.sh` | One KerSor-style round orchestrator |
| `experiments/killtest_23.py` | Mem-bake kill test (NO-GO) |
| `experiments/kill_test_d5.py` | d5 mux kill test (NO-GO) |
| `experiments/analyze_gap.py` | Tail gap measurement |
| `directions/LESSONS.md` | Do-not-repeat registry |

## User guidance (KerSor orchestrator)
- Baseline 1120 (d3-sparse+E2). Beat 1120; PSPACE=0 <= 1187 (now 1180).
- NOT CUDA: evolve VLIW-native workflow on STALL.
- Priority: (1) re-seed omni_anneal on 1134 graph; (2) find ~7 more load-floor cycles to unlock #27; (3) reprice alu→valu repack + tail packing.
- Read: directions/WAVE-5-exotic-strategies.md, directions/LESSONS.md

## Confirmation Needed
- None

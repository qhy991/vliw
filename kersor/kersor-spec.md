# KerSor Spec: VLIW perf_takehome (VERIFIED)

> Human-readable summary. Authoritative content is in sentinel blocks below.
> Use with: `/kersor:optimize --spec kersor/kersor-spec.md` (see experiments/KERSOR_VLIW.md)
> **Important:** CUDA AKW workflows do NOT apply. The agent MUST use local Python tools listed in test-method.md.

## Target

- op: VLIW instruction scheduler (`KernelBuilder.build_kernel`)
- backend: python (combinatorial / no GPU)
- target_speedup: 1.282  (1152 → 1000 cycles; absolute baseline 147734 cycles)
- status: VERIFIED

## Constraints

- Do NOT modify `tests/` or `problem.py`
- Global best gate: `CYCLES <= 1152` (PSPACE=1), PSPACE=0 must stay <= 1189
- Read `directions/LESSONS.md` before any experiment — do not retry listed NO-GO levers
- Active Wave-4: scratch-free load cuts (A2–A5) → partial d4 (B1–B3) → #27 repack if load<1036.7
- KerSor: enable `--allow-workflow-evolution --allow-workflow-authoring`; evolve VLIW-native workflow on STALL

---

## Verified Artifacts (authoritative — edit these blocks)

===KERSOR-BLOCK:contract.env===
op=VLIW-perf_takehome-scheduler
backend=python
kernel_language=python
target_speedup=1.282
seed_origin=provided_kernel
kernel_path=/mnt/user_dir/shihaichao/qinhaiyan/vliw/perf_takehome.py
integration_pattern=standalone
timing_method=submission_tests
metric_contract=cycles
forbid_pytest_wall_as_headline=false
baseline_id=merged-floor-1152
baseline_ms=1152
min_runs=3
require_ci=false
status=VERIFIED
===KERSOR-ENDBLOCK===

===KERSOR-BLOCK:test-method.md===
# Test Method — VLIW perf_takehome @ 1152

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
- Pass: prints `OK`, `CYCLES: N` where N <= current best (1152)
- Also run: `PSPACE=0 python tests/submission_tests.py` (must not regress 1189)

## Baseline
- Baseline Latency (ms): 1152
- Baseline: merged-floor @ 1152 cycles (128.24× over 147734 reference)
- Timing Method: submission_tests
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

## Confirmation Needed
- None
===KERSOR-ENDBLOCK===

===KERSOR-BLOCK:kernel-profile.md===
# Kernel Profile — VLIW @ 1152

- Operation Type: VLIW list-scheduler kernel (Python emitter + greedy scheduler)
- Language: python
- Backend: python
- Integration Pattern: standalone
- Profiler Available: none (use submission_tests cycle count)

## Shape
- forest_height=10, rounds=16, batch_size=256, VLEN=8, K_VEC=32

## Engine profile @ 1152 (PSPACE=1)
```
load  2129  floor 1064.5  <- BINDING
alu  12440  floor 1036.7  (28 slots below load — #27 repack absorbed until load drops)
valu  6017  floor 1002.8
flow    716  floor  716.0
realized 1152 | tail gap ~88
```

## D4_FREE probe (partial prize, #26 NO-GO full table)
- k=64: **1093**; crossover k≈12–14; partial k∈[14,22] → ~1100–1110 if mux fits in 79w scratch
- Full 128w d4 table blocked; cherry-pick #25 recycler → 79 free @1152

## Binding rule
- Rule E (#28): engine-of-op matters — const on load vs add_imm on flow
- Do NOT retry: LESSONS §2–§4 kill registry

## Active levers (Wave-4)
1. A2–A5 scratch-free load cuts (#28 extension, setup reorder)
2. B1 cherry-pick #25 recycler; B2 partial D4_FREE k-sweep
3. #27 alu repack ONLY after load floor < 1036.7
===KERSOR-ENDBLOCK===

===KERSOR-BLOCK:roofline-target.json===
{
  "grounded": true,
  "baseline_cycles": 1152,
  "target_cycles": 1000,
  "realistic_speedup": 1.152,
  "ceiling_cycles": 814,
  "ceiling_note": "D4_FREE k=64; partial k~14-22 ~1100; #27 after load<1036.7",
  "binding_engine": "load"
}
===KERSOR-ENDBLOCK===

===KERSOR-BLOCK:baseline-measurement.json===
{
  "baseline_ms": 1152,
  "metric": "cycles",
  "source": "submission_tests",
  "verified_at": "2026-07-05",
  "branch": "explore/merged-floor"
}
===KERSOR-ENDBLOCK===

===KERSOR-BLOCK:deployment-topology.json===
{
  "role": "standalone",
  "framework": "none",
  "kernel_path_role": "standalone",
  "wholesale_replace_ok": true,
  "note": "Python scheduler — KerSor CUDA workflows are inapplicable; use local tools"
}
===KERSOR-ENDBLOCK===

===KERSOR-BLOCK:deployment-topology.md===
# Deployment Topology

- Kernel Path Role: standalone Python module
- Required Integration: none
- KerSor note: on STALL evolve/author VLIW workflow; fallback `experiments/kersor_vliw_round.sh`
===KERSOR-ENDBLOCK===

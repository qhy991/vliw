# KerSor Spec: VLIW perf_takehome (VERIFIED)

> Human-readable summary. Authoritative content is in sentinel blocks below.
> Use with: `/kersor:optimize --spec kersor/kersor-spec.md` (see experiments/KERSOR_VLIW.md)
> **Important:** CUDA AKW workflows do NOT apply. The agent MUST use local Python tools listed in test-method.md.

## Target

- op: VLIW instruction scheduler (`KernelBuilder.build_kernel`)
- backend: python (combinatorial / no GPU)
- target_speedup: 1.134  (1134 → 1000 cycles; absolute baseline 147734 cycles)
- status: VERIFIED

## Constraints

- Do NOT modify `tests/` or `problem.py`
- Global best gate: `CYCLES <= 1134` (PSPACE=1), PSPACE=0 must stay <= 1187
- Read `directions/LESSONS.md` before any experiment — do not retry listed NO-GO levers
- Landed: #28 const→flow (1156→1152), #30 const_flow_mask (1152→1151), E2 sparse D4_COLD_MASK (1151→1134)
- Active Wave-6: re-anneal 1134 graph > find ~7 more load-floor cycles > resurrect #27 alu repack > tail packing
- KerSor: `--allow-workflow-evolution --allow-workflow-authoring`; use VLIW-native workflows, NOT CUDA

---

## Verified Artifacts (authoritative — edit these blocks)

===KERSOR-BLOCK:contract.env===
op=VLIW-perf_takehome-scheduler
backend=python
kernel_language=python
target_speedup=1.134
seed_origin=provided_kernel
kernel_path=/mnt/user_dir/shihaichao/qinhaiyan/vliw/perf_takehome.py
integration_pattern=standalone
timing_method=e2e
metric_contract=cycles
forbid_pytest_wall_as_headline=false
baseline_id=merged-floor-1134
baseline_ms=1134
min_runs=3
require_ci=false
status=VERIFIED
===KERSOR-ENDBLOCK===

===KERSOR-BLOCK:test-method.md===
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
- Pass: prints `OK`, `CYCLES: N` where N <= current best (1134)
- Also run: `PSPACE=0 python tests/submission_tests.py` (must not regress 1187)

## Baseline
- Baseline Latency (ms): 1134
- Baseline: merged-floor-1134
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
- Baseline 1134 (sparse D4_COLD_MASK). Beat 1134; PSPACE=0 <= 1187.
- NOT CUDA: evolve VLIW-native workflow on STALL.
- Priority: (1) re-seed omni_anneal on 1134 graph; (2) find ~7 more load-floor cycles to unlock #27; (3) reprice alu→valu repack + tail packing.
- Read: directions/WAVE-5-exotic-strategies.md, directions/LESSONS.md

## Confirmation Needed
- None
===KERSOR-ENDBLOCK===

===KERSOR-BLOCK:kernel-profile.md===
# Kernel Profile — VLIW @ 1134

- Operation Type: VLIW list-scheduler kernel (Python emitter + greedy scheduler)
- Language: python
- Backend: python
- Integration Pattern: standalone
- Profiler Available: none (use submission_tests cycle count)

## Shape
- forest_height=10, rounds=16, batch_size=256, VLEN=8, K_VEC=32

## Engine profile @ 1134 (PSPACE=1)
```
load  ~2086  floor 1043.0  <- BINDING
alu   12440  floor 1036.7
valu  ~6150  floor 1025.0
flow    805  floor  805.0
realized 1134 | tail gap ~91
```

## Landed @ 1134
- #28 const→flow N=12: 1156→1152
- #30 const_flow_mask: 1152→1151 (per-instance SA mask over 58 consts)
- E2 sparse D4_COLD_MASK `{25,26,27,29,31,34}`: 1151→1134

## Active levers (Wave-6)
1. Re-seed `experiments/omni_anneal.py` on 1134 graph (combine/extract/offset/const_flow)
2. Sparse load-floor search: need ~7 more load cycles to cross below alu 1036.7
3. If load < alu, resurrect #27 alu→valu repack and tail packing
===KERSOR-ENDBLOCK===

===KERSOR-BLOCK:roofline-target.json===
{
  "grounded": true,
  "baseline_cycles": 1134,
  "target_cycles": 1000,
  "realistic_speedup": 1.134,
  "ceiling_cycles": 814,
  "ceiling_note": "D4_FREE k=64; sparse D4 landed 1134; #27 after load<1036.7",
  "binding_engine": "load"
}
===KERSOR-ENDBLOCK===

===KERSOR-BLOCK:baseline-measurement.json===
{
  "baseline_ms": 1134,
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

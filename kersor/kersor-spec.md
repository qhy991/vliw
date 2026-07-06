# KerSor Spec: VLIW perf_takehome (VERIFIED)

> Human-readable summary. Authoritative content is in sentinel blocks below.
> Use with: `/kersor:optimize --spec kersor/kersor-spec.md` (see experiments/KERSOR_VLIW.md)
> **Important:** CUDA AKW workflows do NOT apply. The agent MUST use local Python tools listed in test-method.md.

## Target

- op: VLIW instruction scheduler (`KernelBuilder.build_kernel`)
- backend: python (combinatorial / no GPU)
- target_speedup: 1.111  (1111 → 1000 cycles; absolute baseline 147734 cycles)
- status: VERIFIED

## Constraints

- Do NOT modify `tests/` or `problem.py`
- Global best gate: `CYCLES <= 1111` (PSPACE=1), PSPACE=0 must stay <= 1187
- Read `directions/LESSONS.md` before any experiment — do not retry listed NO-GO levers
- Landed: #28 const→flow (1156→1152), #30 const_flow_mask (1152→1151), W6-C joint d3×d4 SA (1120→1111)
- Active Wave-6 @ 1111: const→flow/vload load cut (fixed d3+d4) > co-bind SA re-seed > target <1000
- KerSor: `--allow-workflow-evolution --allow-workflow-authoring`; use VLIW-native workflows, NOT CUDA

---

## Verified Artifacts (authoritative — edit these blocks)

===KERSOR-BLOCK:contract.env===
op=VLIW-perf_takehome-scheduler
backend=python
kernel_language=python
target_speedup=1.111
seed_origin=provided_kernel
kernel_path=/mnt/user_dir/shihaichao/qinhaiyan/vliw/perf_takehome.py
integration_pattern=standalone
timing_method=e2e
metric_contract=cycles
forbid_pytest_wall_as_headline=false
baseline_id=merged-floor-1111
baseline_ms=1111
min_runs=3
require_ci=false
status=VERIFIED
===KERSOR-ENDBLOCK===

===KERSOR-BLOCK:test-method.md===
# Test Method — VLIW perf_takehome @ 1111

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
- Pass: prints `OK`, `CYCLES: N` where N <= current best (1111)
- Also run: `PSPACE=0 python tests/submission_tests.py` (must not regress 1187)

## Baseline
- Baseline Latency (ms): 1111
- Baseline: merged-floor-1111
- Baseline Detail: merged-floor @ 1111 cycles (133.0× over 147734 reference)
- Timing Method: e2e
- Baseline Status: present

## Local optimization tools (USE THESE — not CUDA workflows)
| Tool | Purpose |
|------|---------|
| `experiments/anneal_d3d4_joint.py` | Joint d3_gather × d4_cold mask SA (landed 1111) |
| `experiments/omni_anneal.py` | Joint SA: combine/extract/offset (re-seed on 1111 graph) |
| `experiments/kersor_vliw_round.sh` | One KerSor-style round orchestrator |
| `experiments/killtest_23.py` | Mem-bake kill test (NO-GO) |
| `experiments/kill_test_d5.py` | d5 mux kill test (NO-GO) |
| `experiments/analyze_gap.py` | Tail gap measurement |
| `directions/LESSONS.md` | Do-not-repeat registry |

## User guidance (KerSor orchestrator)
- Baseline 1111 (joint d3×d4 masks). Beat 1111; PSPACE=0 <= 1187 (now 1180).
- NOT CUDA: evolve VLIW-native workflow on STALL.
- Priority: (1) const→flow/vload on fixed d3+d4; (2) re-seed combine/xor SA on 1111; (3) target <1000.
- Read: directions/WAVE-5-exotic-strategies.md, directions/LESSONS.md

## Confirmation Needed
- None
===KERSOR-ENDBLOCK===

===KERSOR-BLOCK:kernel-profile.md===
# Kernel Profile — VLIW @ 1111

- Operation Type: VLIW list-scheduler kernel (Python emitter + greedy scheduler)
- Language: python
- Backend: python
- Integration Pattern: standalone
- Profiler Available: none (use submission_tests cycle count)

## Shape
- forest_height=10, rounds=16, batch_size=256, VLEN=8, K_VEC=32

## Engine profile @ 1111 (PSPACE=1)
```
load  ~2086  floor 1043.0  <- BINDING
alu   12440  floor 1036.7
valu  ~6150  floor 1025.0
flow    805  floor  805.0
realized 1111 | load 1083.5 BIND | F 1028.9 | tail 27.5
```

## Landed @ 1111
- #28 const→flow N=12: 1156→1152
- #30 const_flow_mask: 1152→1151 (per-instance SA mask over 58 consts)
- W6-C joint d3×d4 `{0..4,34,35,44,45,50,54}` × `{7,12,16,22,24,33,37}`: 1120→1111

## Active levers (Wave-6)
1. const→flow / vload on 1111 (d3+d4 fixed); see directions/34-wave6-1111-baseline.md (combine/extract/offset/const_flow)
2. Sparse load-floor search: need ~7 more load cycles to cross below alu 1036.7
3. If load < alu, resurrect #27 alu→valu repack and tail packing
===KERSOR-ENDBLOCK===

===KERSOR-BLOCK:roofline-target.json===
{
  "grounded": true,
  "baseline_cycles": 1111,
  "target_cycles": 1000,
  "realistic_speedup": 1.134,
  "ceiling_cycles": 814,
  "ceiling_note": "1111 joint d3×d4 converged; sub-1111 needs const→flow/vload then co-bind",
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

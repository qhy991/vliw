# KerSor Spec: VLIW perf_takehome (VERIFIED)

> Human-readable summary. Authoritative content is in sentinel blocks below.
> Use with: `/kersor:optimize --spec kersor/kersor-spec.md` (see experiments/KERSOR_VLIW.md)
> **Important:** CUDA AKW workflows do NOT apply. The agent MUST use local Python tools listed in test-method.md.

## Target

- op: VLIW instruction scheduler (`KernelBuilder.build_kernel`)
- backend: python (combinatorial / no GPU)
- target_speedup: 1.085  (1085 → 1000 cycles; absolute baseline 147734 cycles)
- status: VERIFIED

## Constraints

- Do NOT modify `tests/` or `problem.py`
- Global best gate: `CYCLES <= 1085` (PSPACE=1), PSPACE=0 must stay <= 1184
- Read `directions/LESSONS.md` before any experiment — do not retry listed NO-GO levers
- Landed: d3×d4 joint SA (1091→1085), genome SA (1092→1091), W7-C (1093→1092)
- Sub-1000 still needs correctness-preserving deep-gather cut; see `directions/46-wave7-1085-journey.md`
- KerSor: `--allow-workflow-evolution --allow-workflow-authoring`; use VLIW-native workflows, NOT CUDA

---

## Verified Artifacts (authoritative — edit these blocks)

===KERSOR-BLOCK:contract.env===
op=VLIW-perf_takehome-scheduler
backend=python
kernel_language=python
target_speedup=1.085
seed_origin=provided_kernel
kernel_path=/mnt/user_dir/shihaichao/qinhaiyan/vliw-w7-optimize/perf_takehome.py
integration_pattern=standalone
timing_method=e2e
metric_contract=cycles
forbid_pytest_wall_as_headline=false
baseline_id=wave7-1085
baseline_ms=1085
min_runs=3
require_ci=false
status=VERIFIED
===KERSOR-ENDBLOCK===

===KERSOR-BLOCK:test-method.md===
# Test Method — VLIW perf_takehome @ 1085

## Environment
- Conda env: `vllm`
- Working directory: `/mnt/user_dir/shihaichao/qinhaiyan/vliw-w7-optimize`
- Default env: `PSPACE=1`

## Correctness
```bash
source /mnt/user_dir/shihaichao/qinhaiyan/miniconda3/etc/profile.d/conda.sh && conda activate vllm
cd /mnt/user_dir/shihaichao/qinhaiyan/vliw-w7-optimize
python parity_check.py && python algebra_check_ported.py
```
- Pass: parity 0 violations; algebra ALL-PASS

## Benchmark (primary metric)
```bash
python tests/submission_tests.py
```
- Pass: prints `OK`, `CYCLES: N` where N <= current best (1085)
- Also run: `PSPACE=0 python tests/submission_tests.py` (must not regress 1184)

## Baseline
- Baseline Latency (ms): 1085
- Baseline: wave7-1085
- Baseline Detail: d3×d4 joint SA + genome tail retune @ 1085 cycles
- Timing Method: e2e
- Baseline Status: present

## Local optimization tools (USE THESE — not CUDA workflows)
| Tool | Purpose |
|------|---------|
| `experiments/anneal_joint_w7c.py` | Joint offset+combine SA (1093→1092) |
| `experiments/anneal_genome_w8.py` | Genome SA + `w7_oracle.py` (1092→1091) |
| `experiments/anneal_d3d4_joint.py` | Joint d3×d4 mask SA (1091→1085) |
| `directions/46-wave7-1085-journey.md` | Full optimization narrative |
| `directions/LESSONS.md` | Do-not-repeat registry |

## User guidance (KerSor orchestrator)
- Baseline **1085** (d3×d4 joint + genome tail). Beat 1085; PSPACE=0 <= 1184.
- NOT CUDA: evolve VLIW-native workflow on STALL.
- Priority: (1) new deep-gather representation that is correctness-preserving, not `GATHER_FREE`; (2) structural traverse/hash deletion; (3) multi-rot tail/objective retune after any structural cut.
- Read: directions/39-wave7-kersor-1094.md, directions/35-orthogonal-axes.md, directions/LESSONS.md

## Confirmation Needed
- None
===KERSOR-ENDBLOCK===

===KERSOR-BLOCK:kernel-profile.md===
# Kernel Profile — VLIW @ 1094

- Operation Type: VLIW list-scheduler kernel (Python emitter + greedy scheduler)
- Language: python
- Backend: python
- Integration Pattern: standalone
- Profiler Available: none (use submission_tests cycle count)

## Shape
- forest_height=10, rounds=16, batch_size=256, VLEN=8, K_VEC=32

## Engine profile @ 1094 (PSPACE=1)
```
load  2071  floor 1035.5
alu   11992 floor  999.3
valu   6189 floor 1031.5
flow    859 floor  859.0
F = (8*valu + alu)/60 = 1025.1
realized 1094 | binding floor 1035.5 | tail 58.5
```

## Landed through 1094
- #28 const→flow N=12: 1156→1152
- #30 const_flow_mask: 1152→1151 (per-instance SA mask over 58 consts)
- W6-C joint d3×d4 `{0..4,34,35,44,45,50,54}` × `{7,12,16,22,24,33,37}`: 1120→1111
- W7 seed: default `B0_CARRY=1`, d3 mask `{0,1,37}`, d4 cold mask `{6,7,9,16,21,23,24,25,29,32,35}`, offset retune: 1111→1094

## Active levers (Wave-7)
1. Correctness-preserving deep gather representation. Wrong-output probes show `GATHER_FREE=1` can schedule at 993, but every real replacement pays valu/flow/scratch tax.
2. Structural traverse/hash deletion. Parameter-only valu cuts are absorbed unless they also reduce the binding floor and tail.
3. Multi-rot tail/objective retune after any structural cut. Current best rotation is 29; rot27-only oracle is stale.
===KERSOR-ENDBLOCK===

===KERSOR-BLOCK:roofline-target.json===
{
  "grounded": true,
  "baseline_cycles": 1094,
  "target_cycles": 1000,
  "realistic_speedup": 1.094,
  "ceiling_cycles": 993,
  "ceiling_note": "Wrong-output GATHER_FREE=1 lower bound is 993; real sub-1000 needs a correctness-preserving deep-gather or structural hash/traverse cut.",
  "binding_engine": "load/valu"
}
===KERSOR-ENDBLOCK===

===KERSOR-BLOCK:baseline-measurement.json===
{
  "baseline_ms": 1094,
  "metric": "cycles",
  "source": "submission_tests",
  "verified_at": "2026-07-06",
  "branch": "explore/wave6-1111"
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

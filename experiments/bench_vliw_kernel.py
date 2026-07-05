#!/usr/bin/env python3
"""VLIW benchmark bridge for KerSor's generalist solver.

Contract (KerSor generalist benchmark_command):
    python bench_vliw_kernel.py <kernel_path> <result_path>
where <kernel_path> is a candidate perf_takehome.py. Writes JSON to
<result_path>:
    {compiled, correct, candidate_latency_ms, eager_latency_ms, speedup, metrics}

"latency" here is CYCLES (the task's metric). speedup = baseline_cycles / cand_cycles
with baseline = 1152 (merged-floor). correct = parity_check + algebra_check_ported
both pass AND submission_tests emits OK. A candidate that regresses PSPACE=0 past
1189 or fails correctness is correct=false.

Each candidate runs in an isolated temp dir (symlinks to the frozen repo files +
the candidate as perf_takehome.py) so parallel evals never collide on the module
name or on tests/__pycache__.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

REPO = "/mnt/user_dir/shihaichao/qinhaiyan/vliw"
CONDA_SH = "/mnt/user_dir/shihaichao/qinhaiyan/miniconda3/etc/profile.d/conda.sh"
BASELINE_CYCLES = 1152
PSPACE0_CEILING = 1189

# repo files the harness needs (imported by name from repo root / tests/)
REPO_FILES = ["problem.py", "parity_check.py", "algebra_check_ported.py",
              "algebra_check.py"]
REPO_DIRS = ["tests"]


def _run(cmd, cwd, timeout=600):
    full = f"source {CONDA_SH} && conda activate vllm && {cmd}"
    try:
        p = subprocess.run(["bash", "-lc", full], cwd=cwd, capture_output=True,
                           text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def _cycles(out):
    m = re.findall(r"CYCLES:\s*(\d+)", out)
    return int(m[0]) if m else None


def measure(kernel_path):
    res = {"compiled": False, "correct": False, "candidate_latency_ms": None,
           "eager_latency_ms": float(BASELINE_CYCLES), "speedup": None,
           "metrics": {}}
    if not os.path.isfile(kernel_path):
        res["metrics"]["error"] = f"kernel not found: {kernel_path}"
        return res

    with tempfile.TemporaryDirectory(prefix="vliw_eval_") as td:
        # isolated workdir: symlink frozen repo files, candidate as perf_takehome.py
        for f in REPO_FILES:
            src = os.path.join(REPO, f)
            if os.path.exists(src):
                os.symlink(src, os.path.join(td, f))
        for d in REPO_DIRS:
            src = os.path.join(REPO, d)
            if os.path.exists(src):
                # copy tests dir (needs its own __pycache__; symlink dir is fine
                # for reads but pycache writes would collide -> real copy)
                dst = os.path.join(td, d)
                os.makedirs(dst, exist_ok=True)
                for tf in os.listdir(src):
                    if tf == "__pycache__":
                        continue
                    os.symlink(os.path.join(src, tf), os.path.join(dst, tf))
        import shutil
        shutil.copy(kernel_path, os.path.join(td, "perf_takehome.py"))

        # a candidate "compiles" if it imports without error
        rc, out, err = _run("python -c 'import perf_takehome'", td)
        if rc != 0:
            res["metrics"]["import_error"] = (err or out)[-800:]
            return res
        res["compiled"] = True

        # correctness: parity + algebra
        rc_p, out_p, err_p = _run("python parity_check.py", td)
        rc_a, out_a, err_a = _run("python algebra_check_ported.py", td)
        parity_ok = rc_p == 0 and ("0 /" in out_p or "mismatches: 0" in out_p
                                   or "0 violations" in out_p.lower()
                                   or re.search(r"\b0\s*/\s*\d+", out_p))
        algebra_ok = rc_a == 0 and "ALL-PASS" in out_a

        # primary metric: PSPACE=1 cycles
        rc1, out1, err1 = _run("PSPACE=1 python tests/submission_tests.py", td)
        cyc1 = _cycles(out1)
        # guard metric: PSPACE=0 must not regress past 1189
        rc0, out0, err0 = _run("PSPACE=0 python tests/submission_tests.py", td)
        cyc0 = _cycles(out0)

        res["metrics"] = {
            "parity_ok": bool(parity_ok), "algebra_ok": bool(algebra_ok),
            "pspace1_cycles": cyc1, "pspace0_cycles": cyc0,
            "pspace0_ceiling": PSPACE0_CEILING,
            "submission_rc_pspace1": rc1, "submission_rc_pspace0": rc0,
        }
        if not parity_ok or not algebra_ok:
            res["metrics"]["fail_reason"] = "correctness (parity/algebra)"
            return res
        if cyc1 is None:
            res["metrics"]["fail_reason"] = "no CYCLES in submission_tests output"
            res["metrics"]["stderr"] = (err1 or out1)[-800:]
            return res
        if cyc0 is not None and cyc0 > PSPACE0_CEILING:
            res["metrics"]["fail_reason"] = f"PSPACE=0 regressed {cyc0}>{PSPACE0_CEILING}"
            return res

        res["correct"] = True
        res["candidate_latency_ms"] = float(cyc1)
        res["speedup"] = round(BASELINE_CYCLES / cyc1, 4)
        return res


def main():
    if len(sys.argv) < 3:
        print("usage: bench_vliw_kernel.py <kernel_path> <result_path>",
              file=sys.stderr)
        sys.exit(2)
    kernel_path, result_path = sys.argv[1], sys.argv[2]
    res = measure(kernel_path)
    with open(result_path, "w") as f:
        json.dump(res, f, indent=2)
    print(json.dumps(res))


if __name__ == "__main__":
    main()

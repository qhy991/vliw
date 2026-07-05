#!/usr/bin/env bash
# Launch helper — run from repo root with conda vllm active.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source /mnt/user_dir/shihaichao/qinhaiyan/miniconda3/etc/profile.d/conda.sh
conda activate vllm

case "${1:-}" in
  w0)
    echo "=== W0: #12 p-space ==="
    python experiments/w0_pspace_algebra.py
    echo "--- PSPACE=1 correctness ---"
    PSPACE=1 python parity_check.py
    PSPACE=1 python algebra_check_ported.py
    PSPACE=1 python tests/submission_tests.py
    ;;
  w1)
    echo "=== W1: #01 D3 grid ==="
    python experiments/w1_d3_grid.py | tee experiments/w1_d3_grid.log
    ;;
  w2)
    echo "=== W2: #13 scratch budget ==="
    python experiments/w2_scratch_budget.py | tee experiments/w2_scratch.log
    ;;
  w3)
    echo "=== W3: #03 parity tables ==="
    python experiments/w3_parity_tables.py | tee experiments/w3_parity.log
    ;;
  w4)
    echo "=== W4: combine sweep ==="
    python experiments/w4_combine_sweep.py | tee experiments/w4_combine.log
    ;;
  *)
    echo "usage: $0 w0|w1|w2|w3|w4" >&2
    exit 1
    ;;
esac

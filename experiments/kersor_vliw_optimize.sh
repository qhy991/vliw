#!/usr/bin/env bash
# VLIW-native KerSor-style multi-round optimizer (replaces CUDA AKW for this task).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROUNDS="${1:-3}"
YOLO="${YOLO:-0}"
export KERSOR_VLIW_DIR="$ROOT/experiments/.kersor-vliw"
mkdir -p "$KERSOR_VLIW_DIR"

# lever sequence per round
LEVERS=(scratch-audit omni-anneal d4-free-probe)

echo "KerSor VLIW optimize — baseline 1156, target 1000, rounds=$ROUNDS"
echo "Spec: $ROOT/kersor/kersor-spec.md"
echo "LESSONS: $ROOT/directions/LESSONS.md"
echo "Log dir: $KERSOR_VLIW_DIR"

for ((r=1; r<=ROUNDS; r++)); do
  idx=$(( (r - 1) % ${#LEVERS[@]} ))
  lever="${LEVERS[$idx]}"
  echo ""
  echo "========== Round $r / $ROUNDS : $lever =========="
  bash "$ROOT/experiments/kersor_vliw_round.sh" "$r" "$lever"
done

echo ""
echo "=== Summary ==="
cat "$KERSOR_VLIW_DIR/summary.txt" 2>/dev/null || true
source /mnt/user_dir/shihaichao/qinhaiyan/miniconda3/etc/profile.d/conda.sh
conda activate vllm
cd "$ROOT"
python tests/submission_tests.py 2>&1 | grep -E 'OK|CYCLES|Speedup'

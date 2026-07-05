#!/usr/bin/env bash
# One KerSor-style optimization round for VLIW (local tools, no CUDA workflows).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROUND="${1:?usage: kersor_vliw_round.sh <round> <lever>}"
LEVER="${2:?usage: kersor_vliw_round.sh <round> <lever>}"
LOG_DIR="${KERSOR_VLIW_DIR:-$ROOT/experiments/.kersor-vliw}"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/round-${ROUND}.log"

source /mnt/user_dir/shihaichao/qinhaiyan/miniconda3/etc/profile.d/conda.sh
conda activate vllm
cd "$ROOT"

echo "=== KerSor VLIW round $ROUND lever=$LEVER $(date -Iseconds) ===" | tee "$LOG"

baseline_cycles() {
  python tests/submission_tests.py 2>&1 | grep -m1 '^CYCLES:' | awk '{print $2}'
}

gate() {
  python parity_check.py 2>&1 | tail -1 | tee -a "$LOG"
  python algebra_check_ported.py 2>&1 | tail -1 | tee -a "$LOG"
  python tests/submission_tests.py 2>&1 | tee -a "$LOG" | tail -5
}

BEFORE="$(baseline_cycles)"
echo "BEFORE=$BEFORE" | tee -a "$LOG"

case "$LEVER" in
  scratch-audit)
    python - <<'PY' | tee -a "$LOG"
import perf_takehome as P
kb = P.KernelBuilder()
kb.build_kernel(10, 2**11-1, 256, 16)
free = 1536 - kb.scratch_ptr
print(f"scratch_ptr={kb.scratch_ptr}/1536 free={free} need_for_d4=128 gap={128-free}")
PY
    echo "Action: implement #25 scratch reclaim in worktree explore/25-scratch-reclaim-d4" | tee -a "$LOG"
    ;;
  omni-anneal)
    ITERS="${ITERS:-12000}"
    echo "Running omni_anneal.py iters=$ITERS (re-seed, no --resume)" | tee -a "$LOG"
    python experiments/omni_anneal.py \
      --classes combine,extract,offset \
      --iters "$ITERS" \
      --confirm-every 500 \
      --out "$LOG_DIR/champ_round_${ROUND}.json" 2>&1 | tee -a "$LOG"
    echo "NOTE: promote champ to perf_takehome.py manually after review" | tee -a "$LOG"
    ;;
  d4-free-probe)
    if grep -q 'D4_FREE' perf_takehome.py 2>/dev/null; then
      D4_FREE=1 python tests/submission_tests.py 2>&1 | tee -a "$LOG" | tail -5
    else
      echo "D4_FREE env not wired — implement probe flag per #26 doc" | tee -a "$LOG"
      python - <<'PY' | tee -a "$LOG"
# Theoretical from #20: delete 512 d4 scalar loads -> ~1088, alu binds
loads = 2140 - 512
print(f"theoretical load floor after full d4 cut: {loads/2:.1f} cycles")
print(f"theoretical realized band: ~1088 (needs real mux + scratch)")
PY
    fi
    ;;
  verify-only)
    gate | tee -a "$LOG"
    ;;
  *)
    echo "Unknown lever: $LEVER" | tee -a "$LOG"
    exit 1
    ;;
esac

AFTER="$(baseline_cycles)"
echo "AFTER=$AFTER delta=$(( BEFORE - AFTER ))" | tee -a "$LOG"
echo "ROUND_${ROUND}_RESULT before=$BEFORE after=$AFTER lever=$LEVER" >> "$LOG_DIR/summary.txt"

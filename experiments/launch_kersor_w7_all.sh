#!/usr/bin/env bash
# Launch all four Wave-7 KerSor lanes in tmux session 3.
set -euo pipefail

PARENT=/mnt/user_dir/shihaichao/qinhaiyan
SCRIPT="$PARENT/vliw-w7-optimize/experiments/launch_kersor_w7.sh"
SESSION=3

declare -a LANES=(
  "w7-a:$PARENT/vliw-w7-a-deep-gather"
  "w7-d:$PARENT/vliw-w7-d-scheduler-objective"
  "w7-c:$PARENT/vliw-w7-c-tail-retune"
  "w7-b:$PARENT/vliw-w7-b-traverse-structure"
)

for entry in "${LANES[@]}"; do
  name="${entry%%:*}"
  root="${entry#*:}"
  tmux kill-window -t "=${SESSION}:${name}" 2>/dev/null || true
  tmux new-window -t "=${SESSION}:" -n "$name"
  bash "$SCRIPT" "$SESSION" "$name" "$root" "$name"
  sleep 20
done
echo "Wave-7 KerSor: tmux session ${SESSION} windows w7-a w7-d w7-c w7-b"

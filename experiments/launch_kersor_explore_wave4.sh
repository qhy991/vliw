#!/usr/bin/env bash
# Launch KerSor /kersor:optimize Wave-4 explore with workflow evolution in tmux W5.
set -euo pipefail

SESSION="${1:-3}"
WIN=5
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROMPTS="$ROOT/experiments/claude-prompts"
DOCS="$ROOT/directions"
KERSOR="/home/qinhaiyan/KerSor"
SPEC="$ROOT/kersor/kersor-spec.md"
CLAUDE="/home/qinhaiyan/.local/lib/node_modules/@anthropic-ai/claude-code/node_modules/@anthropic-ai/claude-code-linux-x64/claude"
BASELINE_CYCLES=1152

KERSOR_CMD="/kersor:optimize $ROOT/kersor --spec $SPEC --mode explore --yolo --allow-workflow-evolution --allow-workflow-authoring --workflow-evolution-budget 8 --workflow-authoring-budget 3 --max-workflows 20 --note \"VLIW Python combinatorial scheduler @1152. NOT CUDA. On STALL: evolve Generalist/KSearch to vliw-native (submission_tests cycles, omni_anneal.py). Read WAVE-4-kersor-explore.md + LESSONS.md. Tier-A scratch-free load first. Beat 1152.\""

pick_token() {
  local w pane tok
  if [[ -n "${ANTHROPIC_AUTH_TOKEN:-}" && "${ANTHROPIC_AUTH_TOKEN:0:3}" == "sk-" ]]; then
    echo "$ANTHROPIC_AUTH_TOKEN"
    return 0
  fi
  for w in 0 1 2 3 4 5; do
    pane="$(tmux capture-pane -t "${SESSION}:$w" -p -S -300 2>/dev/null || true)"
    tok="$(grep -oE 'ANTHROPIC_AUTH_TOKEN=sk-[^[:space:]]+' <<<"$pane" | tail -1 | cut -d= -f2-)"
    if [[ -n "$tok" ]]; then
      echo "$tok"
      return 0
    fi
  done
  return 1
}

reset_pane() {
  tmux send-keys -t "${SESSION}:${WIN}" C-c
  sleep 0.4
  tmux send-keys -t "${SESSION}:${WIN}" q
  sleep 0.2
  tmux send-keys -t "${SESSION}:${WIN}" C-c
  sleep 0.4
  local pane
  pane="$(tmux capture-pane -t "${SESSION}:${WIN}" -p -S -10 2>/dev/null || true)"
  if grep -qE 'bypass permissions|❯' <<<"$pane"; then
    tmux send-keys -t "${SESSION}:${WIN}" C-d
    sleep 0.5
  fi
}

claude_ready() {
  local pane
  pane="$(tmux capture-pane -t "${SESSION}:${WIN}" -p -S -40 2>/dev/null || true)"
  grep -qE 'bypass permissions|❯|permission mode' <<<"$pane" && return 0
  return 1
}

wait_claude() {
  local timeout="${1:-90}" t=0
  while (( t < timeout )); do
    claude_ready && return 0
    sleep 2
    t=$((t + 2))
  done
  echo "WARN: Claude not ready on W5 after ${timeout}s" >&2
  return 1
}

TOKEN="$(pick_token || true)"
if [[ -z "${TOKEN:-}" ]]; then
  echo "ERROR: cannot find ANTHROPIC_AUTH_TOKEN" >&2
  exit 1
fi

echo "==> Pull KerSor"
(cd "$KERSOR" && git pull --ff-only 2>&1) || echo "WARN: KerSor pull failed"

echo "==> W$WIN: KerSor explore Wave-4 @ ${BASELINE_CYCLES} (workflow evolution ON)"
reset_pane "$WIN"

tmux send-keys -t "${SESSION}:${WIN}" "export PATH=/home/qinhaiyan/.local/bin:\$PATH && export GIT_PAGER=cat && export VLIW_ROOT=$ROOT && export VLIW_DOCS=$DOCS && export ANTHROPIC_BASE_URL=https://cloud.infini-ai.com/maas && export ANTHROPIC_AUTH_TOKEN=$TOKEN && export ANTHROPIC_MODEL=claude-opus-4-8 && export ANTHROPIC_DEFAULT_SONNET_MODEL=glm-5.2 && export ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-v4-flash && source /mnt/user_dir/shihaichao/qinhaiyan/miniconda3/etc/profile.d/conda.sh && conda activate vllm && cd $ROOT && echo '=== W5 KerSor Wave-4 explore @ ${BASELINE_CYCLES} ===' && git branch --show-current && git log --oneline -1 && python tests/submission_tests.py 2>&1 | tail -3" C-m
sleep 12

tmux send-keys -t "${SESSION}:${WIN}" "$CLAUDE --permission-mode bypassPermissions" C-m

if wait_claude 90; then
  body="$(cat "$PROMPTS/w5-kersor-explore-wave4.txt")"
  prefix="工作目录: $ROOT | 分支: explore/merged-floor | 基线: ${BASELINE_CYCLES} | Wave-4: $DOCS/WAVE-4-kersor-explore.md | "
  prompt="$(echo "$prefix$body" | tr '\n' ' ' | sed 's/  */ /g')"
  tmux send-keys -t "${SESSION}:${WIN}" C-u
  sleep 0.2
  tmux send-keys -t "${SESSION}:${WIN}" -l "$prompt"
  sleep 0.3
  tmux send-keys -t "${SESSION}:${WIN}" C-m
  sleep 2
  # Send the kersor optimize slash command as a separate line
  tmux send-keys -t "${SESSION}:${WIN}" -l "$KERSOR_CMD"
  sleep 0.3
  tmux send-keys -t "${SESSION}:${WIN}" C-m
  echo "  → Wave-4 KerSor explore + /kersor:optimize sent to W5"
else
  echo "  SKIP (Claude not ready)"
fi

echo ""
echo "Monitor: tmux attach -t $SESSION  # window 5"
echo "Session artifacts: $ROOT/.kersor/<timestamp>/"
echo "Spec: $SPEC"
echo "Directions: $DOCS/WAVE-4-kersor-explore.md"

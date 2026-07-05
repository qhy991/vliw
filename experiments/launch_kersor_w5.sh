#!/usr/bin/env bash
# Launch KerSor VLIW optimize agent in tmux session 3, window 5.
set -euo pipefail

SESSION="${1:-3}"
WIN=5
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROMPTS="$ROOT/experiments/claude-prompts"
DOCS="$ROOT/directions"
KERSOR="/home/qinhaiyan/KerSor"
CLAUDE="/home/qinhaiyan/.local/lib/node_modules/@anthropic-ai/claude-code/node_modules/@anthropic-ai/claude-code-linux-x64/claude"
BASELINE_CYCLES=1156

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
  sleep 0.3
  tmux send-keys -t "${SESSION}:${WIN}" q
  sleep 0.2
  tmux send-keys -t "${SESSION}:${WIN}" C-c
  sleep 0.3
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

echo "==> Pull KerSor updates"
(cd "$KERSOR" && git pull --ff-only 2>&1) || echo "WARN: KerSor pull failed"

echo "==> Window $WIN: KerSor VLIW optimize @ ${BASELINE_CYCLES}"
reset_pane "$WIN"

tmux send-keys -t "${SESSION}:${WIN}" "export PATH=/home/qinhaiyan/.local/bin:\$PATH && export GIT_PAGER=cat && export VLIW_ROOT=$ROOT && export VLIW_DOCS=$DOCS && export ANTHROPIC_BASE_URL=https://cloud.infini-ai.com/maas && export ANTHROPIC_AUTH_TOKEN=$TOKEN && export ANTHROPIC_MODEL=claude-opus-4-8 && export ANTHROPIC_DEFAULT_SONNET_MODEL=glm-5.2 && export ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-v4-flash && source /mnt/user_dir/shihaichao/qinhaiyan/miniconda3/etc/profile.d/conda.sh && conda activate vllm && cd $ROOT && echo '=== W5 KerSor VLIW @ ${BASELINE_CYCLES} ===' && git branch --show-current && git log --oneline -1 && python tests/submission_tests.py 2>&1 | tail -3 && bash experiments/kersor_vliw_round.sh 0 verify-only" C-m
sleep 14

tmux send-keys -t "${SESSION}:${WIN}" "$CLAUDE --permission-mode bypassPermissions" C-m

if wait_claude 90; then
  body="$(cat "$PROMPTS/w5-kersor-vliw.txt")"
  prefix="工作目录: $ROOT
分支: explore/merged-floor
文档: $DOCS
KerSor spec: $ROOT/kersor/kersor-spec.md
集成目标: ${BASELINE_CYCLES} cycles

"
  prompt="$(echo "$prefix$body" | tr '\n' ' ' | sed 's/  */ /g')"
  tmux send-keys -t "${SESSION}:${WIN}" C-u
  sleep 0.2
  tmux send-keys -t "${SESSION}:${WIN}" -l "$prompt"
  sleep 0.3
  tmux send-keys -t "${SESSION}:${WIN}" C-m
  echo "  → KerSor VLIW prompt sent to W5"
else
  echo "  SKIP prompt (Claude not ready)"
fi

echo ""
echo "Done. tmux attach -t $SESSION  # window 5"
echo "  Spec: kersor/kersor-spec.md"
echo "  Orchestrator: bash experiments/kersor_vliw_optimize.sh"

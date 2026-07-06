#!/usr/bin/env bash
# Launch a LOCAL (no KerSor CUDA loop) exploration session in one tmux window.
# Real wins on this Python VLIW task come from local analysis + parity/algebra
# verification, not the generalist KerSor workflow loop. So we only inject the
# axis prompt and let the agent drive local Python SA/probes.
# Usage: launch_local_w6.sh <session> <win> <worktree_root> [axis_label]
set -euo pipefail

SESSION="${1:?session}"
WIN="${2:?win}"
ROOT="${3:?worktree_root}"
LABEL="${4:-w6}"

PROMPT="$ROOT/experiments/claude-prompts/w6-axis.txt"
DOCS="$ROOT/directions"
CLAUDE="/home/qinhaiyan/.local/lib/node_modules/@anthropic-ai/claude-code/node_modules/@anthropic-ai/claude-code-linux-x64/claude"
BASELINE_CYCLES=1111

[[ -f "$PROMPT" ]] || { echo "ERROR: missing prompt $PROMPT" >&2; exit 1; }

pick_token() {
  local w pane tok
  if [[ -n "${ANTHROPIC_AUTH_TOKEN:-}" && "${ANTHROPIC_AUTH_TOKEN:0:3}" == "sk-" ]]; then
    echo "$ANTHROPIC_AUTH_TOKEN"; return 0
  fi
  for w in 0 1 2 3 4 5; do
    pane="$(tmux capture-pane -t "${SESSION}:$w" -p -S -400 2>/dev/null || true)"
    tok="$(grep -oE 'ANTHROPIC_AUTH_TOKEN=sk-[^[:space:]]+' <<<"$pane" | tail -1 | cut -d= -f2-)"
    [[ -n "$tok" ]] && { echo "$tok"; return 0; }
  done
  return 1
}

reset_pane() {
  tmux send-keys -t "${SESSION}:${WIN}" C-c; sleep 0.4
  tmux send-keys -t "${SESSION}:${WIN}" q;   sleep 0.2
  tmux send-keys -t "${SESSION}:${WIN}" C-c; sleep 0.4
  tmux send-keys -t "${SESSION}:${WIN}" C-c; sleep 0.3
  tmux send-keys -t "${SESSION}:${WIN}" C-u; sleep 0.2
}

claude_ready() {
  local pane
  pane="$(tmux capture-pane -t "${SESSION}:${WIN}" -p -S -40 2>/dev/null || true)"
  grep -qE 'bypass permissions|❯|permission mode' <<<"$pane" && return 0
  return 1
}

wait_claude() {
  local timeout="${1:-120}" t=0
  while (( t < timeout )); do
    claude_ready && return 0
    sleep 2; t=$((t + 2))
  done
  echo "WARN: Claude not ready on ${SESSION}:${WIN} after ${timeout}s" >&2
  return 1
}

TOKEN="$(pick_token || true)"
[[ -z "${TOKEN:-}" ]] && { echo "ERROR: cannot find ANTHROPIC_AUTH_TOKEN" >&2; exit 1; }

echo "==> [$LABEL] Reset ${SESSION}:${WIN} and launch LOCAL explorer in $ROOT @ ${BASELINE_CYCLES}"
reset_pane

tmux send-keys -t "${SESSION}:${WIN}" "export PATH=/home/qinhaiyan/.local/bin:\$PATH && export GIT_PAGER=cat && export VLIW_ROOT=$ROOT && export VLIW_DOCS=$DOCS && export ANTHROPIC_BASE_URL=https://cloud.infini-ai.com/maas && export ANTHROPIC_AUTH_TOKEN=$TOKEN && export ANTHROPIC_MODEL=claude-opus-4-8 && export ANTHROPIC_DEFAULT_SONNET_MODEL=glm-5.2 && export ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-v4-flash && source /mnt/user_dir/shihaichao/qinhaiyan/miniconda3/etc/profile.d/conda.sh && conda activate vllm && cd $ROOT && echo '=== $LABEL LOCAL @ ${BASELINE_CYCLES} ===' && git branch --show-current && git log --oneline -1" C-m
sleep 8

tmux send-keys -t "${SESSION}:${WIN}" "$CLAUDE --permission-mode bypassPermissions" C-m

if wait_claude 120; then
  body="$(cat "$PROMPT")"
  prefix="工作目录: $ROOT | 分支已 checkout w6 轴分支 | 基线: ${BASELINE_CYCLES} | 直接用本地 Python 分析+SA/probe 干活，不要跑任何 KerSor workflow。先读 directions/35-orthogonal-axes.md 与本轴 prompt，再开始。 | "
  prompt="$(echo "$prefix$body" | tr '\n' ' ' | sed 's/  */ /g')"
  tmux send-keys -t "${SESSION}:${WIN}" C-u; sleep 0.2
  tmux send-keys -t "${SESSION}:${WIN}" -l "$prompt"; sleep 0.3
  tmux send-keys -t "${SESSION}:${WIN}" C-m
  echo "  -> [$LABEL] LOCAL explorer started on ${SESSION}:${WIN}"
else
  echo "  SKIP [$LABEL] (Claude not ready)"
fi

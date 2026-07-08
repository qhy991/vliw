#!/usr/bin/env bash
# Launch KerSor /kersor:optimize in one tmux window for a Wave-7 lane.
# Usage: launch_kersor_w7.sh <session> <win> <worktree_root> <lane_id>
#   lane_id: w7-a | w7-b | w7-c | w7-d
set -euo pipefail

SESSION="${1:?session}"
WIN="${2:?win}"
ROOT="${3:?worktree_root}"
LANE="${4:?lane_id}"
WIN_IDX="$(tmux list-windows -t "=${SESSION}" -F '#{window_index} #{window_name}' 2>/dev/null | awk -v n="$WIN" '$2==n{print $1; exit}')"
[[ -n "${WIN_IDX:-}" ]] || { echo "ERROR: window ${WIN} not in session ${SESSION}" >&2; exit 1; }
TARGET="${SESSION}:${WIN_IDX}"

case "$LANE" in
  w7-a) PROMPT_NAME=w7-a-deep-gather.txt; LABEL="W7-A deep-gather" ;;
  w7-b) PROMPT_NAME=w7-b-traverse-structure.txt; LABEL="W7-B traverse" ;;
  w7-c) PROMPT_NAME=w7-c-tail-retune.txt; LABEL="W7-C tail/combine" ;;
  w7-d) PROMPT_NAME=w7-d-scheduler-objective.txt; LABEL="W7-D oracle" ;;
  w7-x) PROMPT_NAME=w7-exotic-kersor.txt; LABEL="W8 exotic KerSor" ;;
  *) echo "unknown lane $LANE" >&2; exit 1 ;;
esac

PROMPT="$ROOT/experiments/claude-prompts/$PROMPT_NAME"
DOCS="$ROOT/directions"
SPEC="$ROOT/kersor/kersor-spec.md"
CLAUDE="/home/qinhaiyan/.local/lib/node_modules/@anthropic-ai/claude-code/node_modules/@anthropic-ai/claude-code-linux-x64/claude"
BASELINE_CYCLES=1093

KERSOR_CMD="/kersor:optimize $ROOT/perf_takehome.py --spec $SPEC --mode explore --yolo --allow-workflow-evolution --allow-workflow-authoring --workflow-evolution-budget 10 --workflow-authoring-budget 4 --max-workflows 24"

[[ -f "$PROMPT" ]] || { echo "ERROR: missing $PROMPT" >&2; exit 1; }
[[ -d "$ROOT/kersor" ]] || { echo "ERROR: missing $ROOT/kersor" >&2; exit 1; }

pick_token() {
  local w pane tok
  if [[ -n "${ANTHROPIC_AUTH_TOKEN:-}" && "${ANTHROPIC_AUTH_TOKEN:0:3}" == "sk-" ]]; then
    echo "$ANTHROPIC_AUTH_TOKEN"; return 0
  fi
  for w in 0 1 2 3 4 5 6 7 8 9; do
    pane="$(tmux capture-pane -t "=${SESSION}:$w" -p -S -400 2>/dev/null || true)"
    tok="$(grep -oE 'ANTHROPIC_AUTH_TOKEN=sk-[^[:space:]]+' <<<"$pane" | tail -1 | cut -d= -f2-)"
    [[ -n "$tok" ]] && { echo "$tok"; return 0; }
  done
  return 1
}

reset_pane() {
  tmux send-keys -t "${TARGET}" C-c; sleep 0.4
  tmux send-keys -t "${TARGET}" C-u; sleep 0.2
}

claude_ready() {
  local pane
  pane="$(tmux capture-pane -t "${TARGET}" -p -S -40 2>/dev/null || true)"
  grep -qE 'bypass permissions|❯|permission mode' <<<"$pane" && return 0
  return 1
}

wait_claude() {
  local timeout="${1:-120}" t=0
  while (( t < timeout )); do
    claude_ready && return 0
    sleep 2; t=$((t + 2))
  done
  echo "WARN: Claude not ready on ${TARGET} after ${timeout}s" >&2
  return 1
}

TOKEN="$(pick_token || true)"
[[ -z "${TOKEN:-}" ]] && { echo "ERROR: cannot find ANTHROPIC_AUTH_TOKEN" >&2; exit 1; }

echo "==> [$LABEL] ${TARGET} $ROOT @ ${BASELINE_CYCLES}"
reset_pane

tmux send-keys -t "${TARGET}" "export PATH=/home/qinhaiyan/.local/bin:\$PATH && export GIT_PAGER=cat && export VLIW_ROOT=$ROOT && export VLIW_DOCS=$DOCS && export ANTHROPIC_BASE_URL=https://cloud.infini-ai.com/maas && export ANTHROPIC_AUTH_TOKEN=$TOKEN && export ANTHROPIC_MODEL=claude-opus-4-8 && export ANTHROPIC_DEFAULT_SONNET_MODEL=glm-5.2 && export ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-v4-flash && source /mnt/user_dir/shihaichao/qinhaiyan/miniconda3/etc/profile.d/conda.sh && conda activate vllm && cd $ROOT && echo '=== $LABEL @ $BASELINE_CYCLES ===' && git branch --show-current && git log --oneline -1 && python tests/submission_tests.py 2>&1 | grep CYCLES | head -1" C-m
sleep 8

tmux send-keys -t "${TARGET}" "$CLAUDE --permission-mode bypassPermissions" C-m

if wait_claude 120; then
  body="$(cat "$PROMPT")"
  prefix="工作目录: $ROOT | 基线 ${BASELINE_CYCLES} | "
  prompt="$(echo "$prefix$body" | tr '\n' ' ' | sed 's/  */ /g')"
  tmux send-keys -t "${TARGET}" C-u; sleep 0.2
  tmux send-keys -t "${TARGET}" -l "$prompt"; sleep 0.3
  tmux send-keys -t "${TARGET}" C-m; sleep 2
  tmux send-keys -t "${TARGET}" -l "$KERSOR_CMD"; sleep 0.3
  tmux send-keys -t "${TARGET}" C-m
  echo "  -> [$LABEL] KerSor started"
else
  echo "  SKIP [$LABEL] (Claude not ready)"
fi

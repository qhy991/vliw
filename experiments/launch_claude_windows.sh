#!/usr/bin/env bash
# Launch Claude Code auto-mode agents in tmux session 3, windows 0-4.
# Each window runs in its own git worktree (isolated branches).
set -euo pipefail

SESSION="${1:-3}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROMPTS="$ROOT/experiments/claude-prompts"
DOCS="$ROOT/directions"
CLAUDE="/home/qinhaiyan/.local/lib/node_modules/@anthropic-ai/claude-code/node_modules/@anthropic-ai/claude-code-linux-x64/claude"

declare -a WINS=(
  "0|$ROOT|explore/merged-floor|#14 co-bind polish|w0-cobind.txt"
  "1|$ROOT/explore/03-round-structure|explore/03-round-structure|#B1 valu→alu d2/d3|w1-valu-alu.txt"
  "2|$ROOT/explore/03-round-structure|explore/03-round-structure|#B2 scratch liveness|w2-scratch.txt"
  "3|$ROOT/explore/10-autotuner|explore/10-autotuner|#B3 offset×mask×xor|w3-sweep.txt"
  "4|$ROOT|explore/merged-floor|#14 anneal runner|w4-anneal.txt"
)

pick_token() {
  local w pane tok
  if [[ -n "${ANTHROPIC_AUTH_TOKEN:-}" && "${ANTHROPIC_AUTH_TOKEN:0:3}" == "sk-" ]]; then
    echo "$ANTHROPIC_AUTH_TOKEN"
    return 0
  fi
  for w in 0 1 2 3 4; do
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
  local win="$1"
  tmux send-keys -t "$win" C-c
  sleep 0.3
  tmux send-keys -t "$win" q
  sleep 0.2
  tmux send-keys -t "$win" C-c
  sleep 0.3
  local pane
  pane="$(tmux capture-pane -t "$win" -p -S -10 2>/dev/null || true)"
  if grep -qE 'bypass permissions|❯' <<<"$pane"; then
    tmux send-keys -t "$win" C-d
    sleep 0.5
  fi
}

claude_ready() {
  local win="$1"
  local pane
  pane="$(tmux capture-pane -t "$win" -p -S -40 2>/dev/null || true)"
  grep -qE 'bypass permissions|❯|permission mode' <<<"$pane" && return 0
  grep -qE 'Not logged in|Run /login' <<<"$pane" && return 1
  return 1
}

wait_claude() {
  local win="$1" timeout="${2:-90}"
  local t=0
  while (( t < timeout )); do
    claude_ready "$win" && return 0
    sleep 2
    t=$((t + 2))
  done
  echo "WARN: Claude not ready on $win after ${timeout}s" >&2
  return 1
}

send_prompt() {
  local win="$1" prompt_file="$2" branch="$3" cwd="$4"
  local body prefix prompt
  body="$(cat "$prompt_file")"
  prefix="工作目录: $cwd
分支: $branch
文档目录: $DOCS
集成目标: explore/merged-floor @ 1179 cycles

"
  prompt="$(echo "$prefix$body" | tr '\n' ' ' | sed 's/  */ /g')"
  tmux send-keys -t "$win" C-u
  sleep 0.2
  tmux send-keys -t "$win" -l "$prompt"
  sleep 0.3
  tmux send-keys -t "$win" C-m
  echo "  → prompt sent to $win"
}

setup_window() {
  local idx="$1" cwd="$2" branch="$3" title="$4" prompt_name="$5"
  local win="${SESSION}:${idx}"
  local prompt_file="$PROMPTS/$prompt_name"
  local token="$6"

  echo "==> Window $idx: $title"
  echo "    worktree: $cwd"
  echo "    branch:   $branch"

  reset_pane "$win"

  # Phase 1: env + cd (single atomic command)
  tmux send-keys -t "$win" "export PATH=/home/qinhaiyan/.local/bin:\$PATH && export GIT_PAGER=cat && export VLIW_ROOT=$ROOT && export VLIW_DOCS=$DOCS && export ANTHROPIC_BASE_URL=https://cloud.infini-ai.com/maas && export ANTHROPIC_AUTH_TOKEN=$token && export ANTHROPIC_MODEL=claude-opus-4-8 && export ANTHROPIC_DEFAULT_SONNET_MODEL=glm-5.2 && export ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-v4-flash && source /mnt/user_dir/shihaichao/qinhaiyan/miniconda3/etc/profile.d/conda.sh && conda activate vllm && cd $cwd && echo '=== $title | branch=$branch | pwd=\$(pwd) ==='" C-m
  sleep 4

  # Phase 2: git status + optional merge
  if [[ "$branch" != "explore/merged-floor" ]]; then
    tmux send-keys -t "$win" "git branch --show-current && git log --oneline -1 && (git merge --abort 2>/dev/null || true) && git merge explore/merged-floor -m 'merge: sync 1179 base' || echo 'MERGE CONFLICT'" C-m
    sleep 8
  else
    tmux send-keys -t "$win" "git branch --show-current && git log --oneline -1" C-m
    sleep 2
  fi

  # Phase 3: baseline test
  tmux send-keys -t "$win" "python tests/submission_tests.py 2>&1 | tail -3" C-m
  sleep 12

  # Phase 4: start Claude
  tmux send-keys -t "$win" "$CLAUDE --permission-mode bypassPermissions" C-m

  if wait_claude "$win" 90; then
    send_prompt "$win" "$prompt_file" "$branch" "$cwd"
  else
    echo "  SKIP prompt (Claude not ready on $win)"
  fi
}

TOKEN="$(pick_token || true)"
if [[ -z "${TOKEN:-}" ]]; then
  echo "ERROR: cannot find ANTHROPIC_AUTH_TOKEN (export it or set in a tmux pane)" >&2
  exit 1
fi
echo "Using token (${#TOKEN} chars)"

echo "Launching Claude auto agents in tmux session $SESSION"
for entry in "${WINS[@]}"; do
  IFS='|' read -r idx cwd branch title prompt <<<"$entry"
  setup_window "$idx" "$cwd" "$branch" "$title" "$prompt" "$TOKEN"
  sleep 3
done

echo "Done. Attach: tmux attach -t $SESSION"
echo "Worktree map:"
echo "  W0 → merged-floor (#14 co-bind polish)"
echo "  W1 → 03-round-structure (#B1 valu→alu)"
echo "  W2 → 03-round-structure (#B2 scratch)"
echo "  W3 → 10-autotuner (#B3 sweep)"
echo "  W4 → merged-floor (#14 anneal runner)"

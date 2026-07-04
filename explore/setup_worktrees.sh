#!/usr/bin/env bash
# Create explore/* worktrees on a fresh clone. Idempotent.
# Usage: ./explore/setup_worktrees.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

git fetch origin 2>/dev/null || true

WORKTREES=(
  explore/01-exact-scheduler
  explore/02-hash-opcount
  explore/03-round-structure
  explore/04-modulo-pipeline
  explore/05-cross-vector-share
  explore/06-regalloc-hazards
  explore/07-load-engine-lut
  explore/08-flow-vselect
  explore/09-data-layout
  explore/10-autotuner
  explore/11-dead-code-idx
  explore/merged-floor
)

add_worktree() {
  local path="$1"
  local branch="explore/$(basename "$path")"
  if [[ -d "$path" ]] && [[ -f "$path/.git" || -f "$path/.git" ]]; then
    echo "skip $path (exists)"
    return 0
  fi
  if [[ -d "$path" ]]; then
    echo "skip $path (directory exists, not a worktree?)"
    return 0
  fi
  if git show-ref --verify --quiet "refs/heads/$branch"; then
    git worktree add "$path" "$branch"
  elif git show-ref --verify --quiet "refs/remotes/origin/$branch"; then
    git worktree add -b "$branch" "$path" "origin/$branch"
  else
    echo "warn: no branch $branch — skip $path" >&2
  fi
}

echo "==> worktrees under $ROOT"
for wt in "${WORKTREES[@]}"; do
  add_worktree "$wt"
done

git worktree list

echo ""
echo "Global best: explore/merged-floor (expect CYCLES: 1208)"
echo "Docs: directions/INDEX.md"

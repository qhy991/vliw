#!/usr/bin/env bash
# Sets up 10 isolated git worktrees, one per optimization direction, each on its
# own branch off the current best (c26f78b / opt/structural-search). Each worktree
# gets a copy of its direction doc. Idempotent-ish: skips worktrees that already exist.
set -euo pipefail

REPO="/Users/haiyan-mini/Agent4Kernel/vliw"
WT_ROOT="$REPO/explore"          # worktrees live here (gitignored-friendly location)
BASE_COMMIT="c26f78b"            # current best: 1230 cycles
cd "$REPO"

mkdir -p "$WT_ROOT"

# Direction keys (must match the authored docs' filenames in directions/)
KEYS=(
  01-exact-scheduler
  02-hash-opcount
  03-round-structure
  04-modulo-pipeline
  05-cross-vector-share
  06-regalloc-hazards
  07-load-engine-lut
  08-flow-vselect
  09-data-layout
  10-autotuner
)

for k in "${KEYS[@]}"; do
  wt="$WT_ROOT/$k"
  branch="explore/$k"
  if git worktree list | grep -q "$wt"; then
    echo "SKIP (exists): $wt"
    continue
  fi
  # create branch off the current best if it doesn't exist
  if ! git show-ref --verify --quiet "refs/heads/$branch"; then
    git branch "$branch" "$BASE_COMMIT"
  fi
  git worktree add "$wt" "$branch"
  echo "CREATED: $wt on $branch"
done

echo "=== worktrees ==="
git worktree list

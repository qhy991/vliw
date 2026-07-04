#!/usr/bin/env bash
# One-shot: create the six PLAN-1000 exploration worktrees from explore/merged-floor.
# Run from the repo root (the one containing perf_takehome.py). Idempotent:
# re-running skips worktrees that already exist.
set -euo pipefail

BASE_BRANCH="${BASE_BRANCH:-explore/merged-floor}"
BASE_REPO_ROOT="$(git rev-parse --show-toplevel)"
PARENT="$(dirname "$BASE_REPO_ROOT")"

# name : direction doc
LANES=(
  "15-s2s3-fusion:directions/15-s2s3-fusion.md"
  "16-d4-mux-load-floor:directions/16-d4-mux-load-floor.md"
  "17-omni-anneal-infra:directions/17-omni-anneal.md"
  "18-micro-purges:directions/18-micro-purges.md"
  "19a-2round-fuse:directions/19-moonshots.md"
  "19d-mem-bake:directions/19-moonshots.md"
)

git fetch --all --prune >/dev/null

for lane in "${LANES[@]}"; do
  name="${lane%%:*}"
  doc="${lane##*:}"
  wt_path="${PARENT}/vliw-${name}"
  branch="explore/${name}"

  if git worktree list --porcelain | grep -q "worktree ${wt_path}$"; then
    echo "== ${name}: worktree already exists at ${wt_path}"
  else
    if git show-ref --verify --quiet "refs/heads/${branch}"; then
      echo "== ${name}: reusing existing branch ${branch}"
      git worktree add "${wt_path}" "${branch}"
    else
      echo "== ${name}: creating new branch ${branch} from ${BASE_BRANCH}"
      git worktree add -b "${branch}" "${wt_path}" "${BASE_BRANCH}"
    fi
  fi

  # Verify the baseline in the fresh worktree.
  (
    cd "${wt_path}"
    echo "-- ${name}: baseline verification (should print CYCLES: 1179)"
    python tests/submission_tests.py 2>&1 | grep -E 'CYCLES|OK|FAIL' | head -5
    echo "-- ${name}: direction doc → ${doc}"
  )
done

echo
echo "All worktrees ready under ${PARENT}/vliw-<lane>. Suggested next step:"
echo "  cd ${PARENT}/vliw-15-s2s3-fusion   # start here — biggest verified win"

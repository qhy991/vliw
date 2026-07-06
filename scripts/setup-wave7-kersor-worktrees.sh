#!/usr/bin/env bash
# Create Wave-7 KerSor exploration worktrees from the current 1094 baseline.
# Run from the repo root that contains perf_takehome.py.
set -euo pipefail

BASE_BRANCH="${BASE_BRANCH:-explore/wave6-1111}"
BASE_REPO_ROOT="$(git rev-parse --show-toplevel)"
PARENT="$(dirname "$BASE_REPO_ROOT")"

LANES=(
  "w7-a-deep-gather:directions/39-wave7-kersor-1094.md:Deep gather representation"
  "w7-b-traverse-structure:directions/39-wave7-kersor-1094.md:Traverse/hash structural deletion"
  "w7-c-tail-retune:directions/39-wave7-kersor-1094.md:Multi-rot tail and mask retune"
  "w7-d-scheduler-objective:directions/39-wave7-kersor-1094.md:Scheduler objective and search infrastructure"
)

git fetch --all --prune >/dev/null

echo "Wave-7 base branch: ${BASE_BRANCH}"
echo "Worktrees parent:   ${PARENT}"
echo

for lane in "${LANES[@]}"; do
  IFS=":" read -r name doc label <<<"${lane}"
  wt_path="${PARENT}/vliw-${name}"
  branch="explore/${name}"

  if git worktree list --porcelain | grep -q "worktree ${wt_path}$"; then
    echo "== ${name}: worktree already exists at ${wt_path}"
  else
    if git show-ref --verify --quiet "refs/heads/${branch}"; then
      echo "== ${name}: reusing existing branch ${branch}"
      git worktree add "${wt_path}" "${branch}"
    else
      echo "== ${name}: creating branch ${branch} from ${BASE_BRANCH}"
      git worktree add -b "${branch}" "${wt_path}" "${BASE_BRANCH}"
    fi
  fi

  (
    cd "${wt_path}"
    echo "-- ${name}: ${label}"
    echo "-- doc: ${doc}"
    python tests/submission_tests.py 2>&1 | grep -E 'OK|FAILED|CYCLES' | head -6 || true
    PSPACE=0 python tests/submission_tests.py 2>&1 | grep -E 'OK|FAILED|CYCLES' | head -6 || true
    cat > KERSOR_WAVE7_COMMAND.md <<EOF
# ${name}: ${label}

Read:

- ${doc}
- directions/35-orthogonal-axes.md
- directions/LESSONS.md
- kersor/kersor-spec.md

Run KerSor from this worktree:

\`\`\`bash
/kersor:optimize ./kersor \\
  --spec kersor/kersor-spec.md \\
  --mode explore \\
  --yolo \\
  --allow-workflow-evolution \\
  --allow-workflow-authoring \\
  --workflow-evolution-budget 10 \\
  --workflow-authoring-budget 4 \\
  --max-workflows 24 \\
  --note "Wave-7 @1094 lane ${name}: ${label}. Read ${doc}. Do not use CUDA workflows. Do not modify tests/ or problem.py. Beat 1094 with PSPACE=0 <= 1184, or write a reproducible NO-GO."
\`\`\`

Verification before commit:

\`\`\`bash
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py
PSPACE=0 python tests/submission_tests.py
git diff -- tests/
\`\`\`
EOF
    echo "-- KerSor command note written: ${wt_path}/KERSOR_WAVE7_COMMAND.md"
  )
  echo
done

cat <<EOF
Wave-7 worktrees are ready.

Suggested tmux usage:
  cd ${PARENT}/vliw-w7-a-deep-gather
  # paste the command from KERSOR_WAVE7_COMMAND.md into a KerSor-capable agent.

To change the source branch:
  BASE_BRANCH=<branch-or-commit> scripts/setup-wave7-kersor-worktrees.sh
EOF

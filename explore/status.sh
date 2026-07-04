#!/usr/bin/env bash
# Snapshot the status of all 10 exploration lanes: current cycle count on each
# branch (if perf_takehome.py changed), whether tests/ is still clean, and whether
# a RESULT.md was written. Run anytime: bash explore/status.sh
set -uo pipefail
REPO="/Users/haiyan-mini/Agent4Kernel/vliw"
cd "$REPO"
KEYS=(01-exact-scheduler 02-hash-opcount 03-round-structure 04-modulo-pipeline
      05-cross-vector-share 06-regalloc-hazards 07-load-engine-lut 08-flow-vselect
      09-data-layout 10-autotuner)

printf "%-22s %-8s %-9s %-10s %s\n" "DIRECTION" "CYCLES" "TESTS" "RESULT.md" "LAST_COMMIT"
printf '%.0s-' {1..90}; echo
for k in "${KEYS[@]}"; do
  wt="$REPO/explore/$k"
  [ -d "$wt" ] || { printf "%-22s missing worktree\n" "$k"; continue; }
  # cycle count: build in the worktree (fast ~single build; skip if you want speed)
  cyc=$(cd "$wt" && timeout 240 python3 -c "import perf_takehome as P; kb=P.KernelBuilder(); kb.build_kernel(10,2**11-1,256,16); print(len(kb.instrs))" 2>/dev/null || echo "ERR")
  # tests clean?
  if [ -z "$(git -C "$wt" diff origin/main -- tests/ 2>/dev/null)" ]; then tests="clean"; else tests="DIRTY!"; fi
  rmd=$([ -f "$wt/RESULT.md" ] && echo "yes" || echo "-")
  lc=$(git -C "$wt" log --oneline -1 2>/dev/null | cut -c1-40)
  printf "%-22s %-8s %-9s %-10s %s\n" "$k" "$cyc" "$tests" "$rmd" "$lc"
done
echo
echo "baseline to beat: 1230   throughput floor: 1174"
echo "attach a lane: tmux attach -t 0  (then Ctrl-b <window#>)"

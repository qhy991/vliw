#!/usr/bin/env bash
# Launches an autonomous `claude` session in each of the 10 tmux windows (session 0),
# one per optimization direction. Each session is cd'd into its own worktree,
# runs with --dangerously-skip-permissions --effort max, and is fed a self-contained
# prompt that points it at its direction doc + the shared grounding.
#
# Usage: bash explore/launch_tmux.sh
# Prereq: tmux session "0" with >=10 windows already exists; direction docs written
#         to explore/<key>/DIRECTION.md by the authoring step.
set -euo pipefail

REPO="/Users/haiyan-mini/Agent4Kernel/vliw"
WT_ROOT="$REPO/explore"
SESSION="0"

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

# Build the per-session prompt. Kept as a single line (no raw newlines) so it can be
# sent as one argument to `claude -p`-style invocation; we use interactive mode so the
# agent can iterate, but seed it with this first message.
make_prompt() {
  local key="$1"
  cat <<EOF
You are an autonomous performance engineer working a LONG-RANGE optimization of a VLIW SIMD kernel. Your assigned direction is "$key".

READ FIRST, IN FULL: ./DIRECTION.md (your assigned plan), ./OPTIMIZATION_NOTES.md (verified facts + what is already exhausted), ./perf_takehome.py (KernelBuilder.build_kernel, _emit_vec_round, Scheduler), ./problem.py (the Machine ISA).

GOAL: beat the current best of 1230 cycles, ideally well below it, following YOUR DIRECTION.md. This is a hard, multi-hour effort — do not stop at the first small win; keep pushing toward the throughput floor (1174) or below.

MEASUREMENT (authoritative): cycles == len(kb.instrs) since n_groups==1, and it is data-independent, so you can iterate fast by counting bundles: python3 -c "import perf_takehome as P; kb=P.KernelBuilder(); kb.build_kernel(10, 2**11-1, 256, 16); print(len(kb.instrs))". But EVERY result you keep MUST be confirmed by the real test: python tests/submission_tests.py  (must print OK + a CYCLES line; it runs 8 correctness checks on UNSEEDED random inputs).

ABSOLUTE RULES: (1) NEVER modify anything under tests/ (including tests/frozen_problem.py) — git diff origin/main -- tests/ must stay empty; violating this makes your result INVALID. (2) Only edit perf_takehome.py. (3) Correctness first: final mem[inp_values_p:...] must match the reference for arbitrary inputs.

WORKFLOW: iterate in this worktree (branch explore/$key). Commit progress to this branch as you go with clear messages. When you achieve a verified improvement below 1230, record the exact cycle count and diff in a file RESULT.md at the worktree root. If your direction turns out to be a dead end, document WHY in RESULT.md honestly (that is valuable too). Work autonomously; you have permission to run any needed commands (pip install ortools etc. if your direction needs it). Begin by reading DIRECTION.md and forming a concrete plan.
EOF
}

for i in "${!KEYS[@]}"; do
  key="${KEYS[$i]}"
  win="$i"                       # window index == direction index (0..9)
  wt="$WT_ROOT/$key"
  prompt="$(make_prompt "$key")"

  # cd into the worktree in that window
  tmux send-keys -t "${SESSION}:${win}" "cd '$wt'" C-m
  # launch claude interactively, permissions bypassed, effort max (highest CLI value;
  # 'ultracode' is NOT a valid --effort CLI value, only an in-session /effort command),
  # seeded with the prompt. Prompt passed via temp file to avoid shell-quoting issues.
  pf="$wt/.launch_prompt.txt"
  printf '%s\n' "$prompt" > "$pf"
  tmux send-keys -t "${SESSION}:${win}" "claude --dangerously-skip-permissions --effort max \"\$(cat .launch_prompt.txt)\"" C-m
  # upgrade to ultracode (xhigh + dynamic workflow orchestration) via the in-session
  # slash command; queues until the first turn completes, then applies.
  sleep 2
  tmux send-keys -t "${SESSION}:${win}" "/effort ultracode"
  sleep 1
  tmux send-keys -t "${SESSION}:${win}" C-m
  echo "launched window $win -> $key (effort: max -> ultracode)"
done

echo "All 10 sessions launched. Attach with: tmux attach -t 0"

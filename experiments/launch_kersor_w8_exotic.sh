#!/usr/bin/env bash
# Launch Wave-8 exotic KerSor on w7-d worktree.
set -euo pipefail
SCRIPT="$(cd "$(dirname "$0")" && pwd)/launch_kersor_w7.sh"
ROOT=/mnt/user_dir/shihaichao/qinhaiyan/vliw-w7-d-scheduler-objective
bash "$SCRIPT" 3 w7-d "$ROOT" w7-x

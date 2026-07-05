# KerSor VLIW Optimize — command reference

KerSor's default AKW workflows target **CUDA/GPU** kernels. This VLIW task is a
**Python combinatorial scheduler** — use the VLIW-native path below.

## Command (Claude Code / Cursor)

```text
/kersor:vliw-optimize
```

Implemented as a shell orchestrator (not a KerSor plugin slash command):

```bash
cd /mnt/user_dir/shihaichao/qinhaiyan/vliw
bash experiments/kersor_vliw_optimize.sh [--rounds N] [--yolo]
```

## KerSor plugin path (optional, with spec)

If running inside KerSor-enabled Claude with `--yolo`, the agent should **NOT**
dispatch CUDA workflows. Instead:

```text
/kersor:optimize /mnt/user_dir/shihaichao/qinhaiyan/vliw/kersor \
  --spec /mnt/user_dir/shihaichao/qinhaiyan/vliw/kersor/kersor-spec.md \
  --yolo --max-workflows 1 \
  --note "VLIW Python scheduler: skip CUDA workflows; run experiments/kersor_vliw_round.sh each round; read directions/LESSONS.md"
```

On `STALLED` (expected for CUDA catalog), fall through to local orchestrator.

## One round

```bash
bash experiments/kersor_vliw_round.sh <round_id> <lever>
```

Levers: `scratch-audit` | `omni-anneal` | `d4-free-probe` | `verify-only`

## Loop in Claude Code

```text
/loop 60m 继续 kersor vliw optimize：读 LESSONS.md 和 Wave-3 方向，跑 kersor_vliw_round.sh 下一杠杆，beat 1156 或 NO-GO 后停止
```

## Success criteria

- `python tests/submission_tests.py` → OK, CYCLES < 1156
- parity + algebra pass
- PSPACE=0 not worse than 1190

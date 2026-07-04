# VLIW optimization roadmap (1208 baseline)

**Repo:** https://github.com/qhy991/vliw  
**Global best:** branch `explore/merged-floor` — **1208 cycles** (122.30×)

## Fresh machine setup

```bash
git clone https://github.com/qhy991/vliw.git
cd vliw
git fetch origin
./explore/setup_worktrees.sh
cd explore/merged-floor
python tests/submission_tests.py   # CYCLES: 1208
```

## Documentation

- **`directions/INDEX.md`** — direction ranking, deprecated list, execution order
- **`explore/merged-floor/RESULT.md`** — landed stack + engine profile
- **`explore/merged-floor/DIRECTION.md`** — integration branch next steps

## Active work (op-count route)

1. **#12 p-space** — store parity `p` not `idx` (−256 valu)
2. Re-sweep combine mask + per-position offset
3. **#01** D3 gather tail + combine_tail grid
4. **#13** mem spill → **#03** phase-2 d2/d3 (−320 valu)

Scheduling (#01 CP-SAT, #04, #09) is **exhausted** (≤3 cycles left).

## Worktree workflow

Each `explore/<name>/` is a git worktree on `explore/<name>`. Land wins on
`explore/merged-floor`; verify with `submission_tests.py` after every change.

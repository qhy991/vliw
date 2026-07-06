# O1+O3 stack union test @ 1111 (2026-07-06)

**Branch:** `explore/v111-alu-cut`  
**Probe:** `experiments/probe_o1o3_stack.py`  
**O1 proxy:** `GATHER_FREE=1` — delete all depth≥4 node fetches (wrong output;
schedule-length only; alu becomes binding).  
**O3 lever:** `B0_CARRY=1` — b0-carry extract elimination (gated, default OFF).

## Result: STACK UNION **PASS**

| case | realized | load | alu | valu | F | bind | tail |
|------|---------:|-----:|----:|-----:|--:|-----:|-----:|
| baseline | **1111** | 1083.5 | 1036.7 | 1027.0 | 1028.9 | load | 27.5 |
| O3 alone | 1118 (+7) | 1083.5 | 972.0 | 1023.7 | 1013.3 | load | 34.5 |
| O1 alone | **1057** (−54) | **87.5** | 1014.7 | 964.2 | 974.3 | alu | 42.3 |
| **O1+O3 union** | **997** (−114) | **87.5** | **940.7** | 963.2 | 958.7 | valu | 33.8 |

### Stacking arithmetic (perfect additivity)

```
O1 gain on baseline:      1111 → 1057  (−54c)
O3 gain on load-cut:      1057 → 997   (−60c)
Union vs baseline:        1111 → 997   (−114c = −54 + −60)
O3 alone on baseline:     1111 → 1118  (+7c regression, as predicted)
```

### Orthogonality contract

- **load floor:** O1=87.5, union=87.5 (Δ0) — O3 does not touch load ✓
- **alu floor:** O1=1014.7 → union=940.7 (−74c) — pure alu elimination ✓
- **F floor:** O1=974.3 → union=958.7 (−15.6c) ✓
- Shipped baseline byte-identical at 1111; `B0_CARRY=1` alone → 1118 (gate fail, expected)

## Interpretation

1. **O3 alone cannot ship on 1111** — alu is 47c sub-floor; b0-carry removes
   tail-packing filler → +7c regression (1111→1118).

2. **O3 stacks cleanly once O1 makes alu bind** — on the load-cut proxy,
   b0-carry drops realized a further **60c** with zero load-floor change.

3. **Additivity is exact** on this proxy (−54 + −60 = −114). The two levers
   edit disjoint code paths (`GATHER_FREE` depth≥4 skip vs `B0_CARRY` depth-2/3
   extract) and do not fight for slots on the load-cut graph.

4. **Note on O1 proxy strength:** `directions/36-O3-alu-cut.md` cited a weaker
   partial cut (D4_FREE k≈24 → 1102→1073, −29c stack). `GATHER_FREE=1` models
   the **full** gather removal (all depths ≥4), giving a stronger load-cut
   (1057) and proportionally larger stack gain (−60c). The stacking *mechanism*
   is the same; only the O1 prize size differs.

## Integration contract

Ship order when real O1 lands (scratch-reclaim / d4-table):
1. Land O1 load-floor cut on `explore/wave6-1120` (verify load < alu).
2. Enable `B0_CARRY=1` in env A/B — expect ~12–60c further drop depending on
   how far O1 cuts load (floor-cap vs tail-repack).
3. Re-run O2 valu fusion only after `max(load, alu) < valu ~1024`.

Reproduce:
```bash
python experiments/probe_o1o3_stack.py
```

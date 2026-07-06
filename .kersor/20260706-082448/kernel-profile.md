# Kernel Profile — VLIW @ 1134

- Operation Type: VLIW list-scheduler kernel (Python emitter + greedy scheduler)
- Language: python
- Backend: python
- Integration Pattern: standalone
- Profiler Available: none (use submission_tests cycle count)

## Shape
- forest_height=10, rounds=16, batch_size=256, VLEN=8, K_VEC=32

## Engine profile @ 1134 (PSPACE=1)
```
load  ~2086  floor 1043.0  <- BINDING
alu   12440  floor 1036.7
valu  ~6150  floor 1025.0
flow    805  floor  805.0
realized 1134 | tail gap ~91
```

## Landed @ 1134
- #28 const→flow N=12: 1156→1152
- #30 const_flow_mask: 1152→1151 (per-instance SA mask over 58 consts)
- E2 sparse D4_COLD_MASK `{25,26,27,29,31,34}`: 1151→1134

## Active levers (Wave-6)
1. Re-seed `experiments/omni_anneal.py` on 1134 graph (combine/extract/offset/const_flow)
2. Sparse load-floor search: need ~7 more load cycles to cross below alu 1036.7
3. If load < alu, resurrect #27 alu→valu repack and tail packing

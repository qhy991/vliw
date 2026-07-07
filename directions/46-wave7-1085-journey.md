# Wave-7 优化历程：1093 → 1085（2026-07-07）

本文档归纳 `explore/w7-optimize` 分支上，从 **1093** 一路压到 **1085 cycles**（PSPACE=1）的完整路径、每步机制与复现命令。当前 global best：**1085**（PSPACE=0 **1181**）。

---

## 1. 总览

| 阶段 | cycles | Δ | 杠杆类型 | 工具 / 分支 |
|------|--------|---|----------|-------------|
| W7 基线 | 1093 | — | B0 + sparse d3/d4 + rot29 offset + combine #1304 | `67301ba` |
| **W7-C** | **1092** | −1 | 联合 tail packing（offset + combine） | `anneal_joint_w7c.py` |
| **Wave-8 genome** | **1091** | −1 | 同上，更深联合 SA（666 valu combines） | `anneal_genome_w8.py` + `w7_oracle.py` |
| **d3×d4 joint** | **1085** | −6 | 稀疏 mask 协同重搜（load↔flow 重分配） | `anneal_d3d4_joint.py` |

**累计：1093 → 1085（−8 cycles）**

核心规律：

1. **单轴 SA 在 1093/1092 已耗尽** — 单独 flip combine、单独 step offset、d4 贪心扩展、key_idx 扫描均无 win。
2. **联合搜索才能逃逸局部最优** — offset 与 combine 必须耦合 perturb；d3 与 d4 mask 必须 joint anneal。
3. **两类杠杆正交、可叠加** — tail packing（op 总数不变）与 sparse gather/mux（load↔flow shuffle）作用于不同维度，按顺序落地可叠乘。

---

## 2. 引擎地板演进

```
                load    valu    alu     F       bind    tail
1093 baseline   1035.5  1031.7   998.7  1025.1  load    ~57.5
1092 (W7-C)     1035.5  1048.8   930.0  1025.1  valu    ~43.2
1091 (genome)   1035.5  1052.8   914.0  1025.1  valu    ~38.2
1085 (d3×d4)    1043.5  1056.3   914.7   961.9  valu    ~28.7
```

解读：

- **1092/1091**：纯调度 win。load floor 不动；把更多 hash XOR combine 从 alu 挪到 valu（642→666），在 windup/drain 填 valu 空洞，缩短 tail。
- **1085**：mask win。realized 下降来自 **tail 再压 ~10c** + 新 d3/d4 窗口让 load-idle 段更好吃 flow/mux 税；load floor 略升（1035.5→1043.5）但仍 sub bind，由 valu 绑定。

---

## 3. 分步详解

### Step A：1093 → 1092（W7-C joint offset + combine）

**问题：** 在 1093 图上，单轴 `anneal_pos_offset`（rot29）和单 bit combine 扫描均 flat @1093。

**做法：** `experiments/anneal_joint_w7c.py` — 每步同时扰动 `_POS_OFFSET_PSPACE_32x16`（32 int）与 `_COMBINE_VALU_PSPACE_32x16`（1536 bool）。

**Oracle：** min over rotations `{25, 27, 29}`（单 rot29 在 offset 变异上会误判 +10c）。

**落地变更：**

- `_COMBINE_VALU_PSPACE_32x16`：539 → **642** valu combines
- `_POS_OFFSET_PSPACE_32x16`：25 处 offset 调整
- commit：`890f7e1`

**机制：** hash stage 的 `_combine` 在 valu（1 slot）与 alu（8 slot）间算术等价；选 engine 只改 packing。联合 SA 找到「更多 valu combine + 特定 windup/drain phasing」的耦合点。

---

### Step B：1092 → 1091（Wave-8 genome SA）

**问题：** W7-C 后 combine+offset 仍是单轴局部最优；需要更快迭代 + 更大步长联合 move。

**做法：**

- 新增 `experiments/w7_oracle.py`：rot-window 快速评估（~1s），floor 精确、cycles 为 proxy
- 新增 `experiments/anneal_genome_w8.py`：JSON genome `{"combine_mask", "pos_offset"}`，每步同时 flip 1–6 combine bits **且** step 1–4 offset 项

**关键 run：** `seed=99, iters=2000, kmax=5, jmax=3` → proxy rot29 **1091**，full-32 确认 **1091**。

**落地变更：**

- valu combines：642 → **666**（+24 net）
- `_POS_OFFSET_PSPACE_32x16`：19 处相对 1092 再调
- champion：`experiments/champ_w8.json`

**机制：** 与 Step A 同类（tail packing），但搜索空间更大（kmax/jmax 更高），在 1092 basin 边缘再抠 1c tail。

---

### Step C：1091 → 1085（d3×d4 joint SA）

**问题：** 纯 tail SA @1091 四轮 genome restart 全部 flat；需动 **load↔flow** 分配。

**做法：** `experiments/anneal_d3d4_joint.py`，gate `GATE1=1091`：

- Phase 1：4×4000 iter SA，联合 flip `D3_GATHER_MASK` × `D4_COLD_MASK`（各 64 bit）
- Phase 2：对 top-40 oracle 候选做 full-32 确认

**最佳 mask（full-32 确认）：**

```text
D3_GATHER_MASK = {0, 2, 39, 41, 44, 57}     # 6/64 instances → scalar gather
D4_COLD_MASK   = {10,11,14,16,17,20,23,25,27,28,31,33}  # 12/64 → cold vload mux
```

（旧 shipped：`d3={0,1,37}`，`d4={6,7,9,16,21,23,24,25,29,32,35}`）

**结果：** PSPACE=1 **1085**，PSPACE=0 **1181**；1503 个 distinct oracle≤1096 mask 中最佳。

**机制：**

- d3 gather：**+8 load / instance**，但可把 gather 放进 load-idle 的 drain 窗口
- d4 cold mux：**−8 load / instance**，付 flow+valu 税，仅在 schedule 友好 slot 净赢
- **协同：** d3 与 d4 单独搜 @1091 均 NO-GO；联合搜才找到 load=1043.5 处 realized 最低的窗口组合

champion：`champ_d3d4_joint.json`

---

## 4. 已验证 NO-GO（勿重烧）

| 方向 | @1091/1085 结果 | 原因 |
|------|-----------------|------|
| d4 mask 单 bit 贪心扩展 | 0/53 win | `probe_w7_d4_expand.py` |
| genome SA @1085（4 restart） | flat 1085 | tail 局部最优 |
| d5 cold mux | +13c best | flow 税 > load 省 |
| depth≥5 gather 删除（正确性破坏） | skip d5–d10 → 1072 错误输出 | 仅 scheduler 下界 |
| `GATHER_FREE=1`（错误输出） | **997c** @1085 图 | 证明 sub-1000 需 **correctness-preserving** deep gather |
| B0_CARRY @1091 | 无收益 | alu 已 sub-floor |
| xor / key_idx 单轴 | 无 win | engine shuffle 吸收 |

---

## 5. 距 sub-1000

@1085 正确实现的地板：

```
valu BIND  1056.3
load       1043.5
tail        28.7
```

`GATHER_FREE` 错误探针 @1085：**1004c**（+81c 名义空间），offset sweep 最佳 **997c** — 调度器有余量，但 **缺少不破坏语义的 depth≥5 gather 替代**（无 `vgather`、d5 tournament 已 NO-GO）。

可行下一步：

1. correctness-preserving deep-gather（mem-side / 跨轮 prefetch）
2. 任何 structural load cut 后 **必须** 在新区间重跑 `anneal_genome_w8` + `anneal_d3d4_joint`（Rule C：禁止 cherry-pick 旧 champ）

---

## 6. 复现

```bash
cd vliw-w7-optimize
source .../conda.sh && conda activate vllm

# 当前 global best
python tests/submission_tests.py              # CYCLES: 1085
PSPACE=0 python tests/submission_tests.py     # CYCLES: 1181
python parity_check.py && python algebra_check_ported.py

# 引擎 profile
python experiments/w7_oracle.py --json

# 重跑各 SA（耗时：genome ~10min/restart，d3d4 ~70min）
SEED=7777 ITERS=6000 python experiments/anneal_joint_w7c.py
python experiments/anneal_genome_w8.py --iters 2000 --seed 99 --restarts 1
ORACLE_ROT=29 GATE1=1091 ITERS=4000 python experiments/anneal_d3d4_joint.py
```

---

## 7. 关键文件索引

| 文件 | 作用 |
|------|------|
| `perf_takehome.py` | shipped 常量：d3/d4 mask、offset、combine |
| `experiments/w7_oracle.py` | 快速 rot-window 评估 |
| `experiments/anneal_genome_w8.py` | combine+offset 联合 genome SA |
| `experiments/anneal_joint_w7c.py` | W7-C 联合 SA（1093→1092 同源） |
| `experiments/anneal_d3d4_joint.py` | d3×d4 联合 SA |
| `experiments/champ_w8.json` | 1091 genome champion |
| `champ_d3d4_joint.json` | 1085 mask champion |
| `directions/LESSONS.md` | NO-GO 注册表 |

---

## 8. 方法论摘要（可复用）

1. **先 profile 再动刀** — `realized = max(floors) + tail`；动 sub-floor engine  payoff=0。
2. **联合搜 > 单轴搜** — 当两轴耦合（offset×combine、d3×d4），必须同一步 mutate。
3. **Oracle 契约** — rot29 快但 offset 变异需 `{25,27,29}` window；新 best 必须 full-32 confirm。
4. **正交杠杆可堆叠** — tail packing（Step A/B）与 mask shuffle（Step C）改不同维度；堆叠顺序：先 mask 改图，再 tail SA 重搜。
5. **sub-1000 需要 elimination** — shuffle 上限 ~1090 段；破 1000 要减少 binding load op（deep gather 表示替换），非更多 engine 分配。

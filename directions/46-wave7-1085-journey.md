# VLIW 优化全史：1230 → 1085（2026-07-07）

本文档归纳 `vliw-w7-optimize` / `explore/w7-optimize` 项目从 **~1230 cycles**（早期
PSPACE=1 栈）到当前 global best **1085**（PSPACE=0 **1181**）的完整优化路径。

绝对 naive 基线为 **147734 cycles**（未调度原始 kernel，`kersor-spec` 中的
`baseline_ms` 对照分母）。本文主链跟踪 **PSPACE=1** 主分数。

**权威 NO-GO 注册表：** [`LESSONS.md`](LESSONS.md)  
**中期栈详情：** [`RESULT.md`](../RESULT.md)  
**方向索引：** [`INDEX.md`](INDEX.md)

---

## 1. 一张表看完主链（有效落地）

| # | 阶段 / Wave | cycles | Δ | 杠杆类型 | 要点 |
|---|-------------|--------|---|----------|------|
| 0 | naive kernel | 147734 | — | — | 无调度 |
| 1 | 早期栈 (#11+#02+#10) | **1230** | — | 混合 | dead-idx、K5-defer、offset+combine |
| 2 | 同上收敛 | **1208** | −22 | tail + defer | 上述组合打磨 |
| 3 | #12 p-space traverse | **1184** | −24 | **消除** | parity `p` 存储，−248 valu |
| 4 | #14 co-bind rebalance | **1179** | −5 | shuffle | 300 valu combines |
| 5 | #15a extract 迁移 | **1174** | −5 | shuffle | 57 extract valu→alu + tail repack |
| 6 | #15 s2+s3 fusion | **1157** | −17 | **消除** | −512 valu；binding 翻转到 load |
| 7 | #18 micro purges | **1156** | −1 | 消除 | p-space 死常量门控 |
| 8 | #28 const→flow | **1152** | −4 | shuffle | 12 setup const → flow |
| 9 | #30 const_flow_mask | **1151** | −1 | shuffle | 58 const 逐实例 SA mask |
| 10 | E2 d4 cold sparse | **1134** | −17 | shuffle | d4 gather→cold mux 窗口 |
| 11 | W6-C joint d3×d4 | **1111** | −23* | shuffle | 相对 1134 图联合 mask（*自 1120 图 −9） |
| 12 | W7 seed | **1094** | −17 | 叠加 | B0_CARRY + 新 d3/d4 + offset |
| 13 | combine #1304 | **1093** | −1 | shuffle | combine mask 重平衡 |
| 14 | W7-C joint SA | **1092** | −1 | tail | offset+combine 联合 |
| 15 | Wave-8 genome SA | **1091** | −1 | tail | 666 valu combines |
| 16 | d3×d4 joint SA | **1085** | −6 | shuffle | 新 mask 协同 @1091 图 |
| | **当前 global best** | **1085** | | | **136.2×** vs naive |

**1230 → 1085：−145 cycles（约 11.8%）**

---

## 2. 按 Wave 分段的优化「轮次」统计

下面每一行是一次**独立落地**或**独立搜索战役**（含有效与无效）。粗算全项目
**约 55–60 轮**，其中 **有效落地 ~18–20 个大台阶**，**无效/NO-GO ~35–40 轮**。

### Wave-1～2（1230 → 1151）：结构消除 + 首次 binding 翻转

**有效落地（9 步）：** 1208 → 1184 → 1179 → 1174 → 1157 → 1156 → 1152 → 1151

| 轮次 | 内容 | 结果 |
|------|------|------|
| W1-1 | #11 dead-idx、#02 K5-defer、#10 offset+combine | → 1208 |
| W1-2 | #03 depth-1 parity-carry | valu −64，**被吸收**（仍 1208） |
| W2-1 | #12 p-space traverse + `anneal_pspace.py` | **1184** |
| W2-2 | #14 `anneal_cobind.py` | **1179** |
| W2-3 | #15a `anneal_extract.py` joint | **1174** |
| W2-4 | #15 s2+s3 muladd fusion + re-anneal | **1157**（load 成 bind） |
| W2-5 | #18 micro purges | **1156** |
| W2-6 | #28 const→flow N=12 | **1152** |
| W2-7 | #30 const_flow_mask SA | **1151** |

**代表性 NO-GO（~15 轮）：**

- #01 D3 gather on p-space → 1201+
- co-bind anneal beyond #14 → flat 1180
- D3-gather anneal → stuck 1184
- #13 mem spill、#19a 2-round hash fuse
- #20 d4 mux engine-split、#21 d5 partial mux
- #22 traverse phase-2、#23 mem-bake K5、#24 tailgap setup pipe
- omni @1156 → flat 1156；CP-SAT / modulo-pipeline ≤3c 差距

### Wave-3～4（1151 → 1111）：load-floor shuffle + scratch 基建

**有效落地（3 步）：** 1134（E2）→ 1120/1111（W6-C）→ recycler 78 free（cycle-neutral）

| 轮次 | 内容 | 结果 |
|------|------|------|
| W3-1 | E2 `D4_COLD_MASK` sparse SA | **1134**（load 1043） |
| W3-2 | #25 scratch recycler cherry-pick | 49→78 free，cycle-neutral |
| W4-1 | W6-C `anneal_d3d4_joint.py` 联合 mask | **1111**（自 1120 −9） |
| W4-2 | O3 `B0_CARRY` alu 消除（gated） | alu −65，@1111 **默认 OFF**（tail 回归） |

**代表性 NO-GO（~10 轮）：**

- #26 d4 table 真实现 → best **1251**（+99）
- #27 alu repack → 前置 floor 不满足
- O4 pos_offset @1111 → flat 1111
- O2 valu fusion → valu sub-floor，吸收
- d5 cold / X1 d5-stream @1111 → 全 NO-GO

### Wave-5～6（1111 → 1093）：W7 seed + combine 精调

**有效落地（2 步）：** 1094（W7 seed）→ 1093（combine #1304）

| 轮次 | 内容 | 结果 |
|------|------|------|
| W5-1 | W7 seed：B0 默认 ON + d3 `{0,1,37}` + d4 新 mask + offset | **1094** |
| W5-2 | combine mask #1304 retune | **1093** |

**代表性 NO-GO（~12 轮）：**

- 1094 上 pos_offset / d3d4 / omni / step / const_flow 全 flat
- d4 expand 贪心 0 win；d5 cold +33c
- W7-A deep-gather、W7-B traverse 删除 → NO-GO
- KerSor CUDA workflow misfire；需本地 `anneal_*.py`

### Wave-7～8 + 近期会话（1093 → 1085）

**有效落地（3 步）：** 1092 → 1091 → 1085

| 轮次 | 内容 | 结果 |
|------|------|------|
| W7-1 | W7-C `anneal_joint_w7c.py` | **1092**（642 valu combines） |
| W8-1 | `anneal_genome_w8.py` + `w7_oracle.py` seed=99 | **1091**（666 combines） |
| W7-2 | `anneal_d3d4_joint.py` 4×4000 @1091 gate | **1085** |

**代表性 NO-GO（本段 ~14 轮）：**

- genome SA 8-restart @1092 flat；4-restart @1085 flat
- joint SA @1085 flat；key_idx / xor / depth skip / rot 穷举
- `GATHER_FREE` 错误探针 997c（不可 ship）
- omni-anneal IndexError；d4 单 bit 扩展 0/53

---

## 3. 引擎 binding 翻转史（为何「shuffle」常常无效）

```
阶段          bind 引擎    典型 load floor   典型 tail
─────────────────────────────────────────────────────
@1174         valu        1070.5            ~75
@1157         load        1070.5→1064.5     ~86
@1134         load        1043              ~
@1111         load        1083.5            ~27.5
@1094         load/valu   1035.5            ~58.5
@1085         valu        1043.5            ~28.7
```

**规律（LESSONS Rule A）：** `realized = max(load, alu, valu, flow, F) + tail`。
在 sub-floor engine 上删 op 或 shuffle，payoff=0，直到该 engine 成为墙。

**三次 binding 翻转：**

1. **#15 后** valu → load（s2+s3 删 512 valu）
2. **E2/W6 后** load 仍 bind，但 mask shuffle 改 tail 而非 floor
3. **@1094** load/valu/F 三墙贴近；@1085 valu 略超 load 成 bind

---

## 4. 两类正交杠杆（全史反复验证）

| 类型 | 做什么 | 典型工具 | 全史代表 |
|------|--------|----------|----------|
| **消除 (elimination)** | 减少 op 总数 | s2+s3 fusion, p-space, micro purge | 1184, 1157 |
| **重分配 (shuffle)** | load↔flow↔alu↔valu 搬家 | combine/extract mask, d3/d4 mask, const→flow | 1179, 1134, 1111, 1085 |
| **纯调度 (tail)** | op 总数不变，改 packing | offset, rotation, joint SA | 1208, 1092, 1091 |

**堆叠契约：**

- shuffle 之间**常常互斥**（cherry-pick 旧 graph champ → 回归）
- 任何 structural/mask 改图后 **必须 re-anneal**（Rule C）
- elimination 才能动 floor；shuffle 上限 ≈ tail gap

---

## 5. Wave-7～8 详解（1093 → 1085）

> 本段为近期 `explore/w7-optimize` 分支上的三步 win；对话记录中常被误当作
> 「项目起点」，实际只是全史末段。

### 5.1 1093 → 1092（W7-C joint offset + combine）

- **工具：** `experiments/anneal_joint_w7c.py`
- **Oracle：** min rotations `{25, 27, 29}`（单 rot29 误判 offset +10c）
- **变更：** 642 valu combines；25 处 offset；commit `890f7e1`
- **机制：** `_combine` engine 选择 + windup/drain phasing 联合逃逸

### 5.2 1092 → 1091（Wave-8 genome SA）

- **工具：** `experiments/w7_oracle.py` + `anneal_genome_w8.py`
- **Run：** seed=99, iters=2000, kmax=5, jmax=3 → full-32 **1091**
- **变更：** 666 valu combines；champ `experiments/champ_w8.json`

### 5.3 1091 → 1085（d3×d4 joint SA）

- **工具：** `experiments/anneal_d3d4_joint.py`（4×4000 iter + top-40 full-32）
- **新 mask：**
  ```text
  D3_GATHER_MASK = {0, 2, 39, 41, 44, 57}
  D4_COLD_MASK   = {10,11,14,16,17,20,23,25,27,28,31,33}
  ```
- **旧 mask：** d3 `{0,1,37}`，d4 `{6,7,9,16,21,23,24,25,29,32,35}`
- **结果：** PSPACE=1 **1085**，PSPACE=0 **1181**；champ `champ_d3d4_joint.json`

### 5.4 @1085 引擎 profile

```
load    1043.5
valu    1056.3  ← BIND
alu      914.7
F        961.9
tail      28.7
```

---

## 6. 距 sub-1000

@1085 正确实现仍距 1000 差 **85c**。

| 探针 | cycles | 说明 |
|------|--------|------|
| 当前 shipped | **1085** | correctness-preserving |
| `GATHER_FREE=1` @1085 | **1004** | **错误输出**，仅 scheduler 下界 |
| + offset sweep | **997** | 同上，不可 ship |

**结论：** sub-1000 需要 **correctness-preserving 的 depth≥5 gather 替代**
（无 `vgather`、d5 tournament / deep-gather 已 NO-GO）。纯 tail SA 在 1085 已穷尽。

---

## 7. 复现

```bash
cd vliw-w7-optimize
source .../conda.sh && conda activate vllm

# 当前 global best
python tests/submission_tests.py              # CYCLES: 1085
PSPACE=0 python tests/submission_tests.py     # CYCLES: 1181
python parity_check.py && python algebra_check_ported.py

# 引擎 profile
python experiments/w7_oracle.py --json

# 重跑 Wave-7/8 SA（耗时）
SEED=7777 ITERS=6000 python experiments/anneal_joint_w7c.py
python experiments/anneal_genome_w8.py --iters 2000 --seed 99 --restarts 1
ORACLE_ROT=29 GATE1=1091 ITERS=4000 python experiments/anneal_d3d4_joint.py
```

---

## 8. 关键文件索引

| 文件 | 作用 |
|------|------|
| `perf_takehome.py` | shipped 常量 |
| `RESULT.md` | Wave-1～2 栈与 #15/#28 详情 |
| `directions/LESSONS.md` | NO-GO 注册表 |
| `directions/33-d3d4-joint-anneal.md` | W6-C 1111 win 文档 |
| `directions/INDEX.md` | 方向索引 @1094 |
| `experiments/anneal_d3d4_joint.py` | d3×d4 联合 SA |
| `experiments/anneal_joint_w7c.py` | offset+combine 联合 SA |
| `experiments/anneal_genome_w8.py` | genome SA |
| `experiments/w7_oracle.py` | 快速评估 |
| `champ_d3d4_joint.json` | 1085 mask champion |
| `experiments/champ_w8.json` | 1091 genome champion |

---

## 9. 方法论摘要（全史沉淀）

1. **先 profile 再动刀** — 弄清 bind 引擎与 tail，再选 elimination vs shuffle。
2. **联合搜 > 单轴搜** — offset×combine、d3×d4 必须耦合 mutate。
3. **禁止跨图 cherry-pick** — 旧 graph 的 champ 在新图上常回归（1115+）。
4. **Oracle 契约** — rot-window proxy + full-32 confirm；offset 变异勿用单 rot29。
5. **Rule C** — 任何 op-count / mask 变更后 re-seed SA，勿 `--resume`  stale champ。
6. **sub-1000 = elimination** — shuffle 在 ~1090 段接近天花板；需 deep-gather 结构突破。

---

## 10. 附录：对话记录 vs 项目全史

| 视角 | 起点 | 终点 | 有效 win 数 |
|------|------|------|-------------|
| **项目全史** | 1230（naive 147734） | **1085** | ~18–20 大台阶 |
| **近期会话** | ~1094/1093 | **1085** | 3 步（1092/1091/1085） |
| **全项目尝试** | — | — | ~55–60 轮（含 NO-GO） |

先前版本本文档仅从 1093 写起，范围偏窄；本版补全 **1230→1085** 主链与分 Wave
轮次统计，作为项目优化史的单一入口文档。

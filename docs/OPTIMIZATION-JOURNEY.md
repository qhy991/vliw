# VLIW Performance Take-Home 优化全历程

> **仓库：** `original_performance_takehome`  
> **固定形状：** `forest_height=10, rounds=16, batch_size=256`  
> **当前 global best：** **1085 cycles**（`explore/w7-optimize`，PSPACE=1；PSPACE=0 **1181**）  
> **基线：** 147734 cycles（纯标量 reference kernel）

本文档按**时间线、分支、杠杆类型**整理全部尝试过的方向，并明确区分：

| 类型 | 含义 | 典型产物 |
|------|------|----------|
| **架构改进** | 改变发射的 op 种类/数量、遍历语义、node 获取方式；正确性不变但**算子图变了** | p-space、s2+s3 融合、depth mux、sparse gather/mux 开关 |
| **参数/搜索** | op 图不变或仅换引擎；通过 mask、offset、rotation、SA 找更紧的 schedule | `_combine_mask`、`_POS_OFFSET_*`、`anneal_*.py` |
| **基础设施** | 不直接降 cycle，但解锁搜索或 scratch | recycler、`w7_oracle.py` |
| **证伪/NO-GO** | 代数、ISA 或实测证明不可行 | 见 §6 |

相关索引：`directions/INDEX.md`、`directions/LESSONS.md`、`directions/46-wave7-1085-journey.md`。

---

## 1. 演进时间线（cycles 里程碑）

```
147734  基线（标量，无向量化/调度）
  ~12k  向量化 + VLIW 调度器 + 浅层 mux + 错峰流水线（早期探索，见 OPTIMIZATION_SUMMARY.md）
  1249  ALU/VALU 再平衡 + head/tail combine 启发式（main @809596c）
  1230  头尾定向 combine rebalance + depth-0 常数折叠（OPTIMIZATION_NOTES.md）
  1208  #11 dead-idx + #02 K5-defer + #10 offset/combine mask（explore/merged-floor 栈起点）
  1184  #12 p-space traverse（−248 valu）+ 重调 mask/offset
  1179  #14 co-bind rebalance
  1174  #15a extract 选择性 valu→alu（联合 anneal）
  1157  #15 s2+s3 muladd 融合（−512 valu）
  1156  #18 micro purges
  1152  #28 const→flow（12 个 setup const 走 flow）
  1151  #30 per-instance const→flow mask（KerSor SA）
  1134  E2 sparse D4_COLD_MASK（6 个 d4 实例 cold mux）
  1120  W6 d3 sparse gather mask（11 个 d3 实例改 gather）— 单轴 SA
  1111  W6-C joint d3×d4 SA（explore/wave6-1111）
  1094  W7 seed：B0_CARRY 默认开 + 新 d3/d4 mask + rot29 offset + combine 表
  1092  W7-C joint offset+combine SA
  1091  Wave-8 genome SA（combine+offset 更深联合搜）
  1085  d3×d4 joint SA 重搜（explore/w7-optimize，当前 best）
```

**从 1249 到 1085 的 −164 cycles 大致构成：**

- **架构 / op-count（约 −80~100c 量级，需叠加 re-anneal 兑现）：** p-space、K5、s2+s3、浅层 mux、dead-idx、micro purges、const→flow 引擎归属
- **稀疏 gather/mux 图 + 联合 SA（约 −50~60c）：** E2 d4 cold、d3 gather、W6-C/W7 d3×d4
- **纯调度 / mask 搜索（约 −10~15c）：** combine/offset/extract 联合 anneal、genome SA、tail packing

---

## 2. 分类框架：架构 vs 参数

### 2.1 架构改进（改了「算什么」）

1. **向量化（VLEN=8）** — 8 路 SIMD，接近 8× 跃迁  
2. **依赖感知 VLIW 调度器** — RAW/WAR/WAW + 多引擎槽位；跨 vector 无 scratch 别名 → 软件流水线  
3. **Hash `multiply_add` 融合** — 3 级 `+` 型 stage 压成 1 个 muladd  
4. **浅层 depth mux（d0–d3）** — broadcast / vselect 锦标赛，消灭浅层 gather  
5. **K5 deferral（#02）** — 7 轮 defer `^K5`，−224 valu  
6. **dead-idx（#11）** — 末轮跳过 idx 更新/存储  
7. **p-space traverse（#12）** — idx 槽存 parity `p`，深轮 traverse 1 muladd，−248 valu  
8. **s2+s3 muladd 融合（#15）** — 再 −512 valu；绑定墙 flip 到 load  
9. **micro purges（#18）** — 删掉 p-space 死路径上的 setup 常量广播  
10. **const→flow（#28/#30）** — `const`（load 引擎）→ `add_imm`（flow 引擎）；**引擎归属变化，op 语义不变**  
11. **D4 cold-table mux（E2 实现）** — 新代码路径：vload tree[15..30] + 运行时 vbroadcast 锦标赛  
12. **D3 sparse gather（W6）** — 部分 d3 实例从 flow-mux **改回** scalar gather（**增加 load**，为 schedule 服务）  
13. **B0_CARRY（O3，架构性消除）** — 删掉冗余 `idx&1` extract，−2048 alu；**默认 gated**（见 §4.3）

### 2.2 参数 / 搜索（改了「怎么排、放哪台引擎」）

| 旋钮 | 作用 | 搜索方式 |
|------|------|----------|
| `_combine_mask` / `_COMBINE_VALU_PSPACE_32x16` | 1536 个 hash XOR combine：valu(1 slot) vs alu(8 slot) | `anneal_cobind.py`、`omni_anneal.py`、`anneal_genome_w8.py` |
| `_xor_mask` | 512 个 `val^=node` 的引擎选择 | 默认规则 `depth>=4 → valu`；可 omni 搜 |
| `_extract_mask` | d2/d3 traverse extract 的引擎 | `anneal_extract.py`（#15a） |
| `_const_flow_mask` | 58 个 const 谁走 flow | KerSor / SA（#30） |
| `_POS_OFFSET_PSPACE_32x16` | 32 vector 发射起始偏移 | `anneal_pos_offset.py`、genome SA |
| `rotation`（0..31） | 32 vector 轮转顺序 | 全 32 rot 取 min；oracle 用 `{25,27,29}` |
| `D3_GATHER_MASK` | 64 个 d3 emit 实例：mux vs gather | `anneal_d3_mask.py`、joint d3×d4 |
| `D4_COLD_MASK` | 64 个 d4 emit 实例：gather vs cold mux | `probe_e2_*`、`anneal_d3d4_joint.py` |
| `COMBINE_HEAD/TAIL` | 早期启发式 | **当前 W7 图已 no-op**（有 explicit mask 时） |
| `key_idx` / `step` / `MTMP_G` | 调度优先级、错峰步长、临时寄存器组数 | 网格扫描；W7 上多数 no-op |

### 2.3 如何区分一次 win 属于哪类

```
若关闭该特性后 op 总数（按引擎分类）变化 → 架构
若 op 总数不变，仅 bundle 数变 → 参数/调度
若 op 总数变但来自「同一算术换引擎」→ 边界情况（如 const→flow：load op↓ flow op↑）
```

**经验法则：** 每次**架构**改动后必须 **re-anneal**（Rule C）；直接 cherry-pick 旧 champ 会回归（LESSONS W6-C stacking rule）。

---

## 3. 分支与实现详解

### 3.1 `main` — 早期地基（~1249）

| 改进 | 类型 | 说明 |
|------|------|------|
| `KernelBuilder` + `Scheduler` | 架构 | 抽象 op 流 + 贪心 list scheduling |
| 向量化 `build_kernel` | 架构 | batch 按 VLEN=8 分组 |
| hash stage 0/4 `multiply_add` | 架构 | 可分配律的 `+` 级融合 |
| depth 0–3 mux | 架构 | 消灭 4/16 轮的 gather |
| stagger `step=4` + 32 rotations | 参数 | 软件流水线相位 |
| XOR combine 默认走 alu（`v_alu_scalar`） | 参数 | valu 6 槽 vs alu 12 槽再平衡 |
| 末轮跳过 idx、条件 wrap、header 编译期 const | 架构 | 合法裁剪 |
| `head=10/tail=100` combine 启发式 | 参数 | OPTIMIZATION_NOTES：−19c 量级 |

**分支状态：** 历史 baseline；后续工作均在 `explore/*` 进行。

---

### 3.2 `explore/merged-floor` — Op-count 主战场（1249→1152）

集成所有「地板移动」类架构 win + 首轮 SA。

| 编号 | 方向 | 类型 | cycles | 机制摘要 |
|------|------|------|--------|----------|
| #11 | dead-idx | 架构 | −（含在 1208 栈） | 最后一轮不写 idx |
| #02 | K5 defer | 架构 | 含在 1208 | 7 轮 defer stage-5 `^K5` |
| #10 | offset + combine mask | 参数 | 1208 | `_POS_OFFSET_*` + per-instance combine |
| #03 ph.1 | depth-1 parity | 架构 | 0（被吸收） | −64 valu，schedule 未兑现 |
| **#12** | **p-space** | **架构** | **1208→1184** | `PSPACE=1`；traverse `p←2p+rem` |
| **#14** | co-bind rebalance | 参数 | 1184→1179 | 300 valu combines（middle→alu） |
| **#15a** | extract→alu | 参数 | 1179→1174 | 57 个 extract 实例；联合 anneal |
| **#15** | s2+s3 fusion | 架构 | 1174→1157 | −512 valu；**必须** re-anneal |
| **#18** | micro purges | 架构 | →1156 | +34 scratch；删死 const |
| **#28** | const→flow | 架构* | 1156→1152 | 前 12 const→`add_imm`；*引擎归属 |
| #10b | idx-space 重扫 | 参数 | PSPACE=0 1189 | 仅 fallback 图 |

**关键 re-anneal：** #15 后 `anneal_extract.py`；#12 后 `anneal_pspace.py`。

**同期证伪（见 RESULT.md）：** #01 D3 gather tail、#13 mem spill、#19a 2-round fuse、co-bind 全空间 SA（1180）、D3-gather anneal（卡 1184）。

---

### 3.3 Wave-4 / KerSor（1152 段）

| 编号 | 分支 | 类型 | 结果 |
|------|------|------|------|
| **#25** | `explore/25-scratch-reclaim-d4` | 基础设施 | **LANDED**：49→80 free words，**0 cycle**；free-list recycler |
| **#30** | KerSor variant-r1 | 参数 | **1152→1151**：`_const_flow_mask` 11 个 const 走 flow |
| **#29** | vaddr→flow | 参数 | **NO-GO**：所有 N>0 回归（vaddr 是 vload RAW 生产者） |
| **#26** | d4 gather cut + real mux | 架构 | **NO-GO**：bit-exact 但 best **1251**（+99）；128w table + pooling 惩罚 |
| **E2** | sparse D4_COLD | 架构+参数 | **1151→1134**：cold mux **实现** + **6 实例 mask 搜索** |

**#26 教训：** `D4_FREE` 探针（错误删除 gather）显示 load floor 可掉到 814、奖品 ~63c，但真实 mux 需要 128w + node/addr pooling，惩罚超过收益。

---

### 3.4 `explore/wave6-1111` — 稀疏 mask 时代（1134→1111）

| 步骤 | 类型 | cycles | 工具/分支 |
|------|------|--------|-----------|
| d3 sparse mask 单轴 SA | 架构开关+参数 | 1134→1120 | `explore/w6-d3-sparse`，`anneal_d3_mask.py` |
| **joint d3×d4 SA** | 参数 | 1120→**1111** | `anneal_d3d4_joint.py`，`explore/w6-c` |

**Shipped @1111：**
```text
D3_GATHER_MASK = {0,1,2,3,4,34,35,44,45,50,54}   # 11/64 → gather
D4_COLD_MASK   = {7,12,16,22,24,33,37}           # 7/64 → cold mux
```

**机制：** d3 gather **加 load**、d4 cold **减 load**；单轴搜看不到协同，必须 64×64 joint SA。赢的是 **tail packing**，不是 load floor 下降（冠军 load 反而偏高 1083.5）。

**Wave-6 正交轴探索 @1111（`35-orthogonal-axes.md`）：**

| 轴 | 分支 | 类型 | 结论 |
|----|------|------|------|
| O1 load | `w6-a-load-floor-consts` | 参数 | NO-GO（const 已在关键路径） |
| O2 valu/F 代数删 op | — | 架构 | NO-GO（hash 刚性） |
| O3 alu b0-carry | `v111-alu-cut` | 架构 | **LANDED gated**：alu 1036→972，但 1111 图 realized +7 |
| O4 tail pos_offset | — | 参数 | NO-GO @1111（结构 tail） |
| scratch | — | 基础设施 | 21w free，E2 需 48w，pool/borrow NO-GO |

---

### 3.5 `explore/w7-optimize` — 当前 best（1094→1085）

详见 `directions/46-wave7-1085-journey.md`。

| 步骤 | 类型 | Δ | 内容 |
|------|------|---|------|
| W7 seed | 架构+参数 | →1094 | `B0_CARRY=1` 默认；新 d3/d4 mask；`_POS_OFFSET_*`；combine 表 #1304 |
| W7-C | 参数 | −1 | `anneal_joint_w7c.py`：offset×combine 联合 SA |
| Wave-8 genome | 参数 | −1 | `anneal_genome_w8.py` + `w7_oracle.py`；valu combines 642→666 |
| d3×d4 joint | 参数 | −6 | 重搜 mask；见下 |

**@1085 shipped mask：**
```text
D3_GATHER_MASK = {0, 2, 39, 41, 44, 57}                    # 6/64
D4_COLD_MASK   = {10,11,14,16,17,20,23,25,27,28,31,33}      # 12/64
```

**引擎剖面 @1085：**
```text
load  1043.5    valu  1056.3 (BIND)    alu  914.7    F  961.9*
realized 1085   tail ~28.7
*注：F 公式 (8·valu+alu)/60；与 LESSONS 中早期 F≈1028 因 combine 分布变化
```

**W7 证伪：** flip-p（代数 OK，perf NO-GO）、PADDR_SPACE（1092→1094）、方案 A 全量 const→flow、store→vload gather（ISA 无 permute）、d5 cold、genome SA @1085 flat、d4 单 bit 扩展 0/53 win。

---

### 3.6 其他 `explore/*` 分支（未合并或 NO-GO）

| 分支 | 议题 | 结论 |
|------|------|------|
| `explore/01-exact-scheduler` | CP-SAT 精确调度 | ≤3c 余量，穷尽 |
| `explore/02-hash-opcount` | hash 代数删 op | s2+s3 复活；R1 旧结论在 valu-bound 下反转 |
| `explore/03-round-structure` | rem-ring / phase-2 | scratch 不够；idx-space only 部分 |
| `explore/04-modulo-pipeline` | 模流水线 | 无 win |
| `explore/20-d4mux-engine-split` | flow vselect d4 mux | scratch 49≪128；flow 1-slot 墙 |
| `explore/21-d5-partial-mux` | d5 mux | 性价比低于 d4 |
| `explore/22-traverse-phase2-valu` | 删 extract | load-bound；最多 −5 stub |
| `explore/23-mem-bake-k5-barrier` | K5 烘进 tree | windup 空槽不够 |
| `explore/24-tailgap-setup-pipe` | setup 与 body 合并 | 1192；intrinsic tail |
| `explore/26-d4-gather-cut` | 真实 d4 mux | NO-GO +99c |
| `explore/27-alu-repack-post-load` | load 降后 alu 再平衡 | 前提未满足 |
| `explore/w6-b-d4-footprint-mix` | d4 footprint | 并入 E2 探针 |
| `explore/w6-e-structural-sub1000` | 结构性 sub-1000 | 无 correctness-preserving win |

---

## 4. 参数搜索工具链

| 脚本 | 搜什么 | 典型收益 | 备注 |
|------|--------|----------|------|
| `anneal_cobind.py` | combine mask | #14：−5c | 全 32 超 #14 无 win |
| `anneal_extract.py` | combine+extract+offset | #15a：−5c | |
| `anneal_pspace.py` | offset+combine @ p-space 图 | #12 后：−24c 兑现 | |
| `omni_anneal.py` | 可配置 genome 类 | 统一框架 | `@1156` 20k iter 无改进 |
| `anneal_d3_mask.py` | D3_GATHER_MASK 64-bit | 1134→1120 | 须 full-space SA |
| `anneal_d3d4_joint.py` | d3×d4 联合 mask | 1120→1111；1091→1085 | **两轴必须联合** |
| `anneal_joint_w7c.py` | offset×combine | 1093→1092 | oracle `{25,27,29}` |
| `anneal_genome_w8.py` | genome JSON | 1092→1091 | kmax/jmax 更大 |
| `w7_oracle.py` | 快速 rot-window 评估 | 基础设施 | ~1s vs full 32 ~10s |
| `anneal_pos_offset.py` | 32 维 offset | @1111 NO-GO | 须 multi-rot oracle |

**Oracle 契约：** 单 rot29 对 offset 变异会误判 +10c；搜索时用 `{25,27,29}`，新 best 必须 **full-32 confirm**。

---

## 5. 架构改进逐项说明

### 5.1 p-space traverse（#12）

- **改什么：** scratch 中 `idx` 槽存 `p`（parity），而非完整树索引；`idx == 2^d - 1 + p`
- **省什么：** 深轮 traverse 从 2 valu（muladd+add）→ 1 muladd（`p ← 2p + rem`）
- **代价：** 每层 gather 需 `fvp_p_d` 广播；+56w setup scratch
- **后续：** 必须 `anneal_pspace.py` 重调 combine/offset

### 5.2 s2+s3 muladd 融合（#15）

- **改什么：** hash stage 2+3 合并为 2 muladd + 1 combine
- **省什么：** −512 valu-locked op
- **关键：** #02 文档曾判死刑（alu-bound 时代）；#12/#14 后 valu-bound，结论反转

### 5.3 E2 D4 cold mux + sparse mask

- **架构：** `_d4_cold_mux_node()` — vload `tree[15..30]`，运行时 2-wide vbroadcast + flow 锦标赛
- **参数：** 仅 **6 个** emit 实例开启（`{25,26,27,29,31,34}` @1134 时代）
- **为何不是 prefix-k：** k=14 时 flow/valu 爆炸（1230+）

### 5.4 D3 sparse gather（W6）

- **架构：** 把部分 d3 **从 mux 改回 gather**（+8 load/实例）
- **悖论：** 全局增加 load，但在 **load-idle 的 drain 窗口** 插入 gather、移走 flow，schedule 更紧
- **参数：** 11 个位置 @1111；W7 重搜为 6 个 @1085

### 5.5 const→flow（#28/#30）

- **架构边界：** 仍是同一立即数，但 `const`（load 槽）→ `add_imm`（flow 槽）
- **#28：** 启发式前 12 个 → −4c
- **#30：** SA 找最优 11 个 → 再 −1c

### 5.6 B0_CARRY（O3）

- **架构：** 删掉 depth-2/3 冗余 `idx&1`，用上一轮 traverse 留在 `addr` 的 rem
- **−2048 alu**，但 @1111 图 extract 是 tail filler → realized **+7c**
- **默认 OFF**；在 load-cut 图（D4_FREE）上 stack 可 **−29c**

---

## 6. 证伪方向总表（勿重烧）

### 6.1 代数 / 结构刚性

- #19a 两轮 hash 融合、O2 valu/F 全删、懒惰折叠中间轮
- hash XOR combine 不可再减（836 个 ^）

### 6.2 ISA 限制

- store→vload 连续化 gather（无 permute）
- 深层 gather 源地址分散，READ 端省不掉

### 6.3 scratch / pooling

- node/addr pooling（G=16 → +163c）
- mtmp 3→1 换 scratch（+19c）
- d4 128w resident table + pooling（#26 实测 +99c）

### 6.4 错误形态的 load mux

- d4/d5 flow vselect 全量 prefix
- d3 gather tail 在 p-space 全开启
- valu-arith select 扩大 cold mask

### 6.5 调度已穷尽

- CP-SAT、key_idx 网格、combine head/tail @ W7
- omni @1156/1085 局部最优
- pos_offset @1111、tail gap 纯 repack
- flip-p、PADDR_SPACE、全量 const→flow

### 6.6 sub-1000 物理下界（@1085 正确实现）

```text
gather + vload 下限 ≈ 1018  （2000+36 load ops / 2）
F 下限 ≈ 1028                 （hash 刚性）
错误输出 GATHER_FREE @1085 ≈ 1004  （仅 scheduler 下界，不可提交）
```

破 1000 需要 **correctness-preserving 的深层 gather 替换** 或 **hash 关键路径缩短**，非更多引擎 shuffle。

---

## 7. 方法论摘要（可写入论文/简历）

1. **先 profile 再动刀：** `realized ≈ max(engine floors, F) + tail`；sub-floor 引擎删 op 收益为 0。
2. **绑定墙会翻转：** 每次大改后重算 floor 层级（valu → load → valu@1085）。
3. **架构改动必须 re-anneal：** mask/offset 索引随 emit order 变；禁止跨图 cherry-pick champ。
4. **shuffle 不可无限堆叠：** combine/xor/const 引擎分配是零和；elimination（s2+s3、K5、p-space）才扩容量。
5. **联合搜索 > 单轴：** offset×combine、d3×d4 必须同步 mutate。
6. **稀疏 mask 赢 tail，不赢 floor：** W6-C/W7 的 −50c 主要来自 schedule 窗口，不是 load op 总数下降。
7. **负结果要记录：** `LESSONS.md` + `directions/*-NOGO.md` 避免重复烧 worktree。

---

## 8. 复现命令

```bash
cd original_performance_takehome

# 当前 best
python tests/submission_tests.py              # CYCLES: 1085
PSPACE=0 python tests/submission_tests.py     # CYCLES: 1181
python parity_check.py && python algebra_check_ported.py
git diff -- tests/                            # 必须为空

# 引擎 profile
python -c "
from collections import Counter
from perf_takehome import KernelBuilder
S={'load':2,'alu':12,'valu':6,'flow':1,'store':2}
kb=KernelBuilder(); kb.build_kernel(10,2047,256,16)
e=Counter()
for b in kb.instrs:
    for k,sl in b.items():
        if k!='debug': e[k]+=len(sl)
print('cycles', len(kb.instrs))
print({k: round(e[k]/S[k],1) for k in S})
print('F', round((8*e['valu']+e['alu'])/60,1))
"
```

---

## 9. 文档与 champion 文件索引

| 路径 | 内容 |
|------|------|
| `OPTIMIZATION_SUMMARY.md` | 早期 1249 方法论 |
| `OPTIMIZATION_NOTES.md` | 1249→1230 头尾 rebalance |
| `RESULT.md` | merged-floor @1152 栈 |
| `PLAN-1000.md` | 1179→1000 计划（部分前提已过期） |
| `directions/LESSONS.md` | NO-GO 注册表 |
| `directions/46-wave7-1085-journey.md` | 1093→1085 逐步 |
| `directions/40-w7-subkilo-plans.md` | sub-1000 七方案证伪 |
| `champ_d3d4_joint.json` | 1085 mask champion |
| `experiments/champ_w8.json` | 1091 genome champion |
| `champ_cobind.json` / `champ_extract.json` | 历史 SA 结果 |

---

*最后更新：2026-07-08，对应 `explore/w7-optimize` @ 1085 cycles。*

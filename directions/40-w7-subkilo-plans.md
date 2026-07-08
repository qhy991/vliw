# Wave-7 @1094 — Sub-1000 方案库（floor 分析 + 7 个候选方案）

> 本文档记录 2026-07-06 从 1094 图出发、朝 sub-1000 目标的一次系统调查：
> 确诊了 realized 的真正瓶颈，证伪了一个代数正确的方向（flip-p），并把
> 剩余的可行路径整理成 7 个分级方案。**所有探针命令可复现。**

**基线：** `explore/wave6-1111` @ **1094**（135.04×），`FLIP_P=0` 默认。
`PSPACE=0` 回退 1184。

---

## 1. 瓶颈确诊：load 墙 + 结构性 tail gap

### 引擎剖面 @1094（PSPACE=1）

```
load  2071 / 2  = 1035.5   ← BINDING（绑定墙）
valu  6189 / 6  = 1031.5
F = (8·valu+alu)/60 = 1025.1
alu  11992 /12  =  999.3
flow   859 / 1  =  859.0
store   32 / 2  =   16.0
realized 1094 | tail gap = 1094 - 1035.5 ≈ 58.5
```

三个高 floor（load / valu / F）挤在 10 周期内——**近简并**。这意味着单砍任一引擎会被另一个吸收，除非同时下降。

### load 的可动性拆解（关键）

```
load 细分: {'load'(gather): 1984, 'vload': 36, 'const': 51}
```

- **1984 gather + 36 vload = 2020 不可移动**，floor = **1010**。
- **51 const 可移动**（→flow via `add_imm`），它们把 floor 从 1010 抬到 1035.5。
- 复现：`python -c "import perf_takehome as P; from collections import Counter;
  kb=P.KernelBuilder(); kb.build_kernel(10,2047,256,16);
  c=Counter(sl[0] for b in kb.instrs for sl in b.get('load',[])); print(dict(c))"`

**推论：合法的 load-floor 下限 = 1010（清空 const），物理下限 = 993（`GATHER_FREE=1` 错误输出）。**

### tail gap 是结构性的（3 个探针一致）

| 探针 | load floor | realized | tail | 结论 |
|---|---|---|---|---|
| baseline | 1035.5 | 1094 | 58.5 | — |
| free-delete d5–d10 gather（错误输出） | 267.5 | **1071** | **71** | floor 崩塌 realized 却不动 |
| free-delete 全部 6144 traverse `-`（错误输出） | valu→999.5 | **1112** | — | 删 valu **反升** |
| skip d6–d10 | 395.5 | 1077 | — | 同上 |

**tail gap 随 floor 下降反而扩大** → windup/drain 阶段 load 引擎天然空转，不是 floor 问题。这与 LESSONS S9/S10 记录一致。**任何只削 valu/alu 的方案都被 load 墙吸收。**

---

## 2. 证伪：flip-p（代数 PASS，性能 NO-GO）

**思路**：depth 1/2/3 的 defer 轮把 traverse 从 2 op（`muladd+sub`）压成 1 op
（`p~' = 2·p~ + rem_x`），奇偶累加器带编译期掩码 `M_d = 2^d−1`，由消费端吸收：
mux 轮交换 vselect 分支；d4/d3 gather 轮读**反转+预异或 K5 的影子表**
（`shadow_d[i] = tree[2^d−1+(i^(2^d−1))] ^ K5`，store 引擎建）；附带 d3 可跨 d4
边界 defer K5。

- **代数正确性：PASS。** `experiments/probe_flip_p.py` — 20×256 元素逐位对齐
  `reference_kernel`。
- **性能：NO-GO。** `experiments/probe_valu_floor.py`：删全部 traverse `-`
  （模拟 flip-p 省的 valu），floor→999.5 但 realized **1094→1112**。收益全在
  valu，被 load 墙吸收，且这些 op 本身是 tail 填充，删了戳破 drain。
- **stacking 也不行**：`cold=11 不删 valu = 1094` vs `cold=11 删 valu = 1112`
  （见 §3 探针）。腾出 valu 余量并没有让 cold-mask 更激进地净降。

**代数正确的 idea，被 realized 的 tail 结构否决。归档到 LESSONS。**

---

## 3. NO-GO 再确认：d4-cold prefix 加大 + 联合 SA

**cold-mask prefix 扫描**（`D4_COLD_MASK` 加大 → load 降但 flow 爆）：

```
shipped(11)  1094  load 1035.5  flow  859
prefix 5     1230  load 1059.5  flow  769
prefix20     1273  load  999.5  flow  994   ← flow 逼近 1 槽墙
prefix64     1847  load  823.5  flow 1654   ← flow 彻底爆炸
```

load 降到 999 时,1-slot flow 涨到 994+、valu 也涨,realized 大幅回退。**现有
11 项稀疏 mask 已是打包最优点。**

**联合 d3×d4 SA**（`experiments/search_w7_joint.py`，3-rot oracle {25,27,29}，
271 iter，从 1094 masks 冷启）：**best = 1094**，无改进。mask 空间局部最优已达。

---

## 4. 方案库（分级，全部朝 load 墙或 tail gap）

### Tier 1 — 有数据支撑，低风险

#### 方案 A：多 zero-seed 打散 const→flow（load floor 1035.5→1012）
- **诡计**：47/51 const 可搬 flow，但现在全读同一 `zero_seed`，setup 的 1-slot
  flow 上 RAW 串行 → 1138。改用 **3~4 个 zero-seed**，退火决定每 const 挂哪个
  seed + 哪些留 load，打散串行链。
- **证据**：强制全搬（`CONST_FLOW_MASK=[1]*58`）→ load floor **1012.0**
  （−47 load），realized 1138（被单 seed 串行卡住，flow 才 906，非容量问题）。
- **可行性**：⭐⭐⭐⭐ `add_imm` 算术精确，零正确性风险。
- **预期**：若 tail 不反弹，realized **1075~1085**。唯一直压 load 墙的合法杠杆。

> **⛔ 方案 A — 已实测全面 NO-GO（2026-07-06）。** 四条路径逐一证伪：
> 1. **多 seed 无效**：诊断 setup 前 60 bundle，flow 恒为 `flow=1`——瓶颈是
>    **1-slot flow 容量**（每周期只能发 1 个 add_imm），不是 RAW 链。加 seed
>    不增 flow 槽。
> 2. **const 延迟出 setup 无效**：const-load 被 setup 的 `broadcast_const`
>    读取（const→vbroadcast），在 setup 关键路径上（探针 dep=True）。
> 3. **vload 常量表无效**：materialize 立即数只能靠 load-const 或 flow-add_imm，
>    无第三条路；广播源仍需标量 const。
> 4. **setup 并入 body 调度流**：跳过 setup 独立 `emit()`，让 body 的 117 load
>    空槽 + 235 flow 空槽吸收——realized **1164**（比 S8 全合并 1192 好，仍
>    +70c）。贪心把 setup 的 const→broadcast→bake RAW 链在 body 高压下拉长。
>
> **根因**：load 引擎全程 94.6% 饱和（2071/2188 槽），空槽只有 117 个且 windup
> 前 50 周期仅 13 个。const 无论怎么挪都在 broadcast 关键路径 + 抢 body 的
> 1-slot flow。**方案 A 死。** 补入 LESSONS。

#### 方案 B：const 派生链（用已算好的 const 造新 const）
- **诡计**：广播常量有算术关系（`m16896=m33·512`、`K2K3=K2+K3`）。不从
  zero_seed 加立即数，而是从**相邻已算 const** 派生（`add_imm`/`<<`），让 flow
  op 沿依赖树分散而非挤源头。
- **可行性**：⭐⭐⭐ 需手工排依赖，合法。配合 A 兑现 1012 floor。

### Tier 2 — 结构性重写，中等风险

#### 方案 C / G：store→vload 把 gather 连续化（**最高赔率**）
- **诡计**：深层 gather 慢因 8 lane 地址不连续。ISA 无跨 lane permute，但
  **`store` 到连续地址 + `vload` 回来 = 免费 gather/scatter**。store floor 仅
  16，有 ~1000 周期纯余量。每轮用 store 把本轮节点按 lane 重排进连续内存，下轮
  `vload`（1 slot 装 8）替代 8 scalar load。
- **证据**：free-delete d5–d10 → load floor 267.5（若能真兑现即破千量级）。
- **可行性**：⭐⭐⭐ 机制 ISA 确定支持。难点：scatter 目标地址依赖 idx，需
  scalar store（2 slot）算地址——成本可能只是从 load 挪到 store/alu，需实测。
- **预期**：唯一能触及 993 下限的机制路径。**建议作为搏千主攻方向。**

> **⛔ 方案 C/G — 机制性 NO-GO（2026-07-06）。** 账本分析暴露根本缺陷：
> **gather 的成本在 READ 端**（源地址 `tree[15+p]` 分散在不连续内存）。
> store→vload 只能让*目标*连续，用于重排**已在寄存器**的数据；但要把
> `mem[tree[15+p_i]]` 从分散内存收集起来，READ 端仍是不连续 gather——**省不掉
> 任何 load**。数据一开始就躺在不连续的内存位置，这是死结。
> - ISA 确认（`problem.py:271-286`）：`load(addr)` = `mem[scratch[addr]]` 单元素
>   间接（gather 原子）；`vload` 只能读**连续** 8 个；**无 gather/scatter 指令、
>   无跨 lane permute**（RESULT.md 顶部早有记载）。
> - 深层 d5–d10 gather = 1536/1984 load，全部卡在"从分散 tree 节点收集"，
>   store↔vload 机制上无法替代。**方案 C/G 死。**

#### 方案 D：位反射 gather 表 + flip-p 影子表复用
- **诡计**：flip-p 单独 NO-GO，但它证明"编译期掩码可被反转 K5-baked 影子表免费
  吸收"。影子表天然按 p 的位反射排列，正好让方案 C 的 vload 命中连续块。
- **可行性**：⭐⭐ 代数已 PASS（`probe_flip_p.py`），难点在调度打包。

### Tier 3 — 稀奇古怪，低成功率

#### 方案 E：跨 group 候选广播复用
- **诡计**：同轮所有 vector 走相同深度，depth d 只有 2^d 个可能节点。depth≤5
  时候选 ≤63 个，一次广播全体共享而非各自 gather。
- **可行性**：⭐⭐ depth 4/5 已用 mux 做类似事；再深 select 成本爆炸（L4 kill）。

#### 方案 F：懒惰求值折叠中间轮
- **诡计**：只有末轮 val 被校验；若能数学折叠中间轮贡献……
- **可行性**：⭐ hash 双射且全位活跃（#19a 证），代数刚性。**几乎必死**，但若赌
  算法突破，这是唯一入口。

---

## 5. 排序建议

| 优先级 | 方案 | 理由 | 预期 |
|---|---|---|---|
| ~~1~~ | ~~A（多 seed const→flow）~~ | **实测 NO-GO**：4 路径全死（§4 Tier1） | — |
| ~~2~~ | ~~B（const 派生链）~~ | 依附 A，A 死则无意义 | — |
| ~~3~~ | ~~C/G（store→vload gather）~~ | **机制 NO-GO**：gather 成本在 READ 端，ISA 无 permute | — |
| 4 | D（位反射影子表 + flip-p） | 依附 C/G 的 vload 命中，C/G 死则无载体 | — |
| 5 | E（跨 group 候选广播） | depth≥5 select 成本爆炸（L4 已 kill） | 低 |
| 6 | F（懒惰求值折叠） | hash 双射全位活跃（#19a 证），代数刚性 | 极低 |

**2026-07-06 收尾结论**：Tier 1（A/B）实测证伪，Tier 2（C/G/D）机制证伪，Tier 3
（E/F）依 LESSONS 早已 kill。**1094 是当前 ISA + hash/树结构下 op-count 路线的
工程极限。** 破千的物理下限 993 需要减少真实 gather 数量，但：
- gather 源（分散 tree 节点）无法用 store↔vload 连续化（无 permute 指令）；
- mux 替代 gather 的 select 成本在 depth≥5 超过收益（L4）；
- 减 valu/alu 被 load 墙吸收，且 traverse op 是 tail 填充（V11）。

**唯一剩余入口 = 算法层面改变 load 足迹**（如证明某些深层节点访问可数学折叠），
这是研究问题，非工程调度问题。当前交付值 **1094（135.04×，9/9 测试通过）**。

---

## 6. 复现命令

```bash
# 瓶颈剖面
python -c "import perf_takehome as P; from collections import Counter; \
  kb=P.KernelBuilder(); kb.build_kernel(10,2047,256,16); \
  S={'load':2,'alu':12,'valu':6,'flow':1,'store':2}; e=Counter(); \
  [e.update({k:len(sl)}) for b in kb.instrs for k,sl in b.items() if k!='debug']; \
  print({k:round(e[k]/S[k],1) for k in S})"

# flip-p 代数（PASS）+ 性能（NO-GO）
python experiments/probe_flip_p.py
python experiments/probe_valu_floor.py

# 方案 A 证据：强制全搬
CONST_FLOW_MASK="$(python -c 'import json;print(json.dumps([1]*58))')" \
  python -c "import perf_takehome as P; from collections import Counter; \
  kb=P.KernelBuilder(); kb.build_kernel(10,2047,256,16); e=Counter(); \
  [e.update({k:len(sl)}) for b in kb.instrs for k,sl in b.items() if k!='debug']; \
  print('load floor', e['load']/2, 'flow', e['flow'])"

# 联合 SA（局部最优确认）
python experiments/search_w7_joint.py

# 验证门（每次落地）
python parity_check.py && python algebra_check_ported.py
python tests/submission_tests.py            # OK, CYCLES <= 1094
PSPACE=0 python tests/submission_tests.py   # OK, CYCLES <= 1184
git diff -- tests/                          # 必须空
```

## 7. 产物索引

| 文件 | 内容 |
|---|---|
| `experiments/probe_flip_p.py` | flip-p 代数 kill-test（20×256 PASS） |
| `experiments/probe_valu_floor.py` | valu-floor 灵敏度探针（flip-p 性能 NO-GO） |
| `experiments/search_w7_joint.py` | 3-rot oracle 联合 d3×d4 SA（局部最优确认） |
| 本文档 | 瓶颈确诊 + 7 方案库 |

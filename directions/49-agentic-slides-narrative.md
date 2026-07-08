# Agentic Native 优化方法论 — Slides 叙述稿

> 用途：对外分享 / 制作演示文稿的精简叙述。
> 详细 SOP 见 [`47-cursor-experiment-agentic-playbook.md`](47-cursor-experiment-agentic-playbook.md)、[`48-cursor-tmux-claude-orchestration.md`](48-cursor-tmux-claude-orchestration.md)。

---

## Slide 1 — 标题

**Agentic Native 驱动的内核优化**

人写契约，Agent 并行探索，确定性工具收网。

交付物是可复用的生产流程与知识沉淀，而不只是更低的 cycles。

---

## Slide 2 — 我们在解决什么

- 优化对象：VLIW 指令调度器（多引擎、强耦合、搜索空间巨大）
- 真正难点：不是「写更快代码」，而是 **架构改动 × 引擎归属 × 调度相位** 的联合搜索
- 实验目标：验证多 Agent 能否替代传统「专家手写 + 手工试错」

---

## Slide 3 — 核心方法：人写契约，不写内核

编排者只定义三层契约：

| 层级 | 内容 |
|------|------|
| **指标契约** | CYCLES、PSPACE=0 护栏、正确性 gate |
| **结构契约** | bind 引擎、tail gap、当前图上的局部最优 |
| **搜索契约** | joint 变量、NO-GO 列表、proxy → full-32 确认流程 |

子 Agent 只需读 **方向文档 + 任务卡 + LESSONS** 即可开工，不必读全仓库历史。

---

## Slide 4 — 系统分工

```
人类        → 定目标、验收 bind 是否变化
Cursor      → 写契约、开 tmux、集成、收网、沉淀文档
tmux × Claude Auto → 独立 worktree 内自主探索
KerSor      → 多轮 workflow 搜索（带 domain spec）
本地 SA     → 已知旋钮空间的确定性长跑
```

**两条原则：**
- 编排者与执行者分离
- 并行必须是 worktree 隔离，不是 window 隔离

---

## Slide 5 — 四代编排演进

| 代 | 做法 | 关键教训 |
|----|------|----------|
| **0** | tmux 跑裸 Python 脚本 | 无闭环、文件冲突 → 已废弃 |
| **1** | Claude Auto + 任务卡 | 一车道一 worktree |
| **2** | + KerSor explore | 必须写 VLIW spec，防 CUDA workflow misfire |
| **3** | 四车道并行 + 集成树 | 只收 verified win |
| **4** | Cursor 跑本地 SA | Agent 探索结构，Python 收网 |

---

## Slide 6 — 标准六步 SOP

每轮优化都走同一条路径：

```
Profile → Cheap Kill → Joint Search → Proxy → Full-32 Gate → Archive
```

**三条铁律：**
1. 先看 **bind 引擎变没变**，不看单点 cycle 偶然波动
2. **图变了就重搜**（Rule C），旧 champ 只能当 seed
3. **NO-GO 是资产**，写进 LESSONS，避免下一 agent 重烧

---

## Slide 7 — Explore vs Exploit

| 阶段 | 执行者 | 适合 |
|------|--------|------|
| **探索** | Opus Auto + KerSor | 结构改动、写 probe、开新方向 |
| **收网** | 本地 `anneal_*.py` | offset×combine、d3×d4 等联合 SA |

**切换信号：** KerSor STALL、cheap probe 证伪、bind 引擎未变。

---

## Slide 8 — 任务卡与产物分级

### 任务卡五段（`claude-prompts/*.txt`）

1. 基线（分支、cycles、引擎 floor）
2. 唯一问题（一句话、可证伪）
3. 禁止重复（引用 LESSONS）
4. 第一探针（cheap kill 命令）
5. Win / Kill（阈值 + gate + NO-GO 文档路径）

### 产物四级

| 级别 | 内容 |
|------|------|
| **Ship** | 进 `perf_takehome.py` + commit |
| **Champion** | `champ_*.json`，作 seed 不一定 ship |
| **NO-GO** | `directions/*-NOGO.md` + LESSONS |
| **错误下界** | 如 GATHER_FREE，信息性不可 ship |

---

## Slide 9 — 模型分工

> 以下基于 launch 脚本、KerSor 配置与对话记录中有证据的部分。

| 角色 | 模型 | 职责 |
|------|------|------|
| 并行探索 Worker | **Claude Opus Auto** | 改代码、写 probe、多车道探索 |
| KerSor 子任务 | GLM-5.2 / DeepSeek-v4-flash | 路由判断、机械操作 |
| 总编排者 | **Cursor Agent / Composer** | 写契约、集成、文档、启动 SA |
| 收网 | **无 LLM** | 确定性 SA |

---

## Slide 10 — 模型 × 任务匹配

| 任务类型 | 最佳执行者 |
|----------|------------|
| 架构性改动（p-space、s2+s3 融合） | Opus Auto |
| 并行多方向探索 | Opus × N（tmux） |
| 长跑数值搜索 | 本地 Python SA |
| 集成 / SOP / 编排脚本 | Cursor Composer |
| 最终 win 判断 | 测试 gate，不靠模型「感觉」 |

**三个转折点：**
1. **Cursor 手写 → Claude Auto** — 用户纠正分工，编排者不再直接改内核
2. **KerSor 无 spec → VLIW-native spec** — 防止搜到 CUDA 错误领域
3. **Agent STALL → 本地 SA 收网** — 越接近局部最优，LLM 边际收益越低

---

## Slide 11 — 人机协作

**人类只做三件事：**
1. 定目标（如 sub-1000，或先打 load floor）
2. 验收结构变化（bind / tail，不是单点 cycles）
3. 决定继续探索还是收网

其余全部 Agent 化：写文档、并行探索、多轮搜索、归档 NO-GO。

---

## Slide 12 — 结语

Agentic Native 不是「让 AI 写一个更快 kernel」，而是把优化变成 **可编排、可并行、可传承** 的生产系统：

| 组件 | 角色 |
|------|------|
| **Opus** | 发明杠杆 |
| **KerSor** | 放大探索半径 |
| **Composer** | 总编排与沉淀 |
| **本地 SA** | 榨干已知空间 |

最终资产：文档链（46/47/48/49）+ LESSONS + launch 脚本 + probe 库。  
下次优化从 **已知边界** 出发，而非从零试错。

---

## 配套文档

| 文档 | 内容 |
|------|------|
| [`46-wave7-1085-journey.md`](46-wave7-1085-journey.md) | 全史复盘 |
| [`47-cursor-experiment-agentic-playbook.md`](47-cursor-experiment-agentic-playbook.md) | 搜索与验证 SOP |
| [`48-cursor-tmux-claude-orchestration.md`](48-cursor-tmux-claude-orchestration.md) | tmux + Claude 编排手册 |
| [`LESSONS.md`](LESSONS.md) | 禁止重试注册表 |

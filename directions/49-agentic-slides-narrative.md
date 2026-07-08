# Agentic Native 优化方法论 — Slides 叙述稿（10 页）

> 对外分享用。详细 SOP：[`47`](47-cursor-experiment-agentic-playbook.md) / [`48`](48-cursor-tmux-claude-orchestration.md)。

---

## Slide 1 — 标题

**Agentic Native 内核优化**

Cursor 编排 · worktree 并行 · Claude 执行 · 知识沉淀

交付物是**可复用流程 + 已知边界**，不只是更低 cycles。

---

## Slide 2 — 问题与目标

- **对象：** VLIW 调度器 — 多引擎、强耦合、三维搜索（架构 × 引擎归属 × 调度相位）
- **目标：** 用多 Agent 替代「专家手写 + 手工试错」
- **验收：** 不看偶然 cycle 波动，看 **bind 引擎是否变化、tail 是否真缩**

---

## Slide 3 — 总流程

```
你 → 定目标 / 验收结构变化
Cursor 主编排器 → 拆方向、写契约、建 worktree、集成、记 LESSONS
tmux × Claude Auto（每车道一 worktree）→ 自主改代码、跑探针
收网 → 本地 anneal_*.py 或编排器后台 SA
```

**原则：** 编排者写契约不写内核；并行 = worktree 隔离。

---

## Slide 4 — 子 Agent 两条执行路径

| 路径 | 适用 | 风险 |
|------|------|------|
| **Claude + Humanize** | 单一架构假设，计划-实现-审查 | 计划过窄 |
| **Claude + KerSor** | 方向不清，多 workflow 探索 | 无 domain spec 会 misfire |
| **本地 SA（无 LLM）** | 已知旋钮联合搜索 | 无法发明新杠杆 |

**六步 SOP：** Profile → Cheap Kill → Joint Search → Proxy → Full-32 Gate → Archive

---

## Slide 5 — 三层契约

| 层级 | 内容 |
|------|------|
| 指标 | CYCLES、PSPACE=0、parity/algebra/submission |
| 结构 | bind 引擎、tail gap、当前图局部最优 |
| 搜索 | joint 变量、NO-GO、proxy→full-32 |

任务卡五段：基线 → 唯一问题 → 禁止重复 → 第一探针 → Win/Kill  
产物：Ship / Champion / NO-GO / 错误下界

---

## Slide 6 — 教训一：集成悖论

> **并行解决广度，集成解决图一致性 — 后者往往更难。**

- 多车道都能赢，**不等于能叠加**：mask / offset / combine 强耦合
- 不同图上的 champ **不能直接 cherry-pick**（Rule C）
- **集成 ≠ merge，是在目标图上 re-anneal**

---

## Slide 7 — 教训二：SA 漂移

> **cycles 越低，Agent 越理性地滑向多参数 SA，而非架构优化。**

| 阶段 | 主要杠杆 |
|------|----------|
| 1230→1157 | elimination（p-space、s2+s3） |
| 1157→1111 | shuffle（d3/d4 mask、const→flow） |
| 1111→1085 | tail SA（offset×combine、joint mask） |
| 1085→1000 | 需 deep-gather 等**新表示**，SA 已 flat |

SA flat + bind 不变 = **切换信号**，不是「再跑一轮」。

---

## Slide 8 — 教训三：编排器也会局部最优

LESSONS 防**重烧死路**，不防**不知道下一条路**。

| 陷阱 | 表现 |
|------|------|
| 指标局部最优 | 连续小步 -1c，bind 不动 |
| 工具局部最优 | 反复调 SA seed/restart |
| 文档局部最优 | LESSONS 变厚，瓶颈未变 |

**停手条件：** bind N 轮不变 + SA flat → 强制结构探针或宣告 NO-GO。

---

## Slide 9 — 模型分工

| 角色 | 谁 | 做什么 |
|------|-----|--------|
| 探索 Worker | Opus Auto（tmux） | 架构改动、probe、多车道 |
| 总编排 | Cursor Composer | 契约、集成、文档、启动 SA |
| 收网 | Python SA | 确定性联合搜索 |
| 判断 | 测试 gate | 不靠模型「感觉」 |

---

## Slide 10 — Takeaway

**多 Agent 优化是两个问题：**
1. **发现杠杆** — 并行探索擅长
2. **在一致图上兑现** — 集成 + re-anneal，更难

**主编排器职责：** 不是堆更多 win，而是在 SA 收益递减时**把算力切回架构层**。

最终资产：文档链 + LESSONS + launch 脚本 + probe 库 → 从**已知边界**出发，而非从零试错。

# Cursor Experiment Playbook（Agentic Native Driven）

> 适用范围：本仓库 VLIW 优化实验，沉淀自 `1230 -> 1085` 全程。
> 目标：把「一次性试错」变成「可复制的多 agent 生产流程」。

## 1. 实验定位

- 这是 **Cursor 的 agentic native driven 实验**。
- 交付物不只是更低 cycles，还包括：
  - 可复用的搜索脚本
  - 可复盘的冠军/失败证据
  - 可传承的 NO-GO 规则

## 2. 三层契约（必须先写清）

- **L1 指标契约**
  - 主指标：`PSPACE=1` 的 `CYCLES`
  - 护栏：`PSPACE=0` 不回归
  - 正确性：`parity + algebra + submission_tests`
- **L2 结构契约**
  - 当前 bind 引擎是谁
  - tail 大小与可压缩空间
  - 当前图（graph）上的已知局部最优
- **L3 搜索契约**
  - 哪些变量必须 joint mutate
  - 哪些方向已 NO-GO（禁止重烧）
  - proxy/full 的确认流程

## 3. 标准工作流（每轮都按这个跑）

1. **Profile**
   - 先跑引擎 floor（load/valu/alu/flow/F）与 tail
2. **Cheap kill probes**
   - 用最短实验先证伪明显死路
3. **Joint search**
   - 对耦合变量做联合 SA（如 offset×combine、d3×d4）
4. **Two-stage confirm**
   - 先 proxy（rot-window），再 full-32 确认
5. **Gate**
   - 通过 correctness + PSPACE=0 gate 才能 ship
6. **Archive**
   - 更新 champ JSON、LESSONS、方向文档

## 4. 关键方法论

- **先看瓶颈翻转，不看单点偶然**
  - 如果 bind 没变或 tail 没缩，通常只是噪声
- **单轴搜索默认不可信**
  - 局部最优常来自变量耦合，必须 joint 才能跳盆地
- **图变了就重搜**
  - 任何 mask/op-count 变化都视为新图，旧 champ 只能做 seed
- **错误下界也有价值**
  - 像 `GATHER_FREE` 虽不可 ship，但可证明调度空间上限
- **NO-GO 是资产，不是失败**
  - 明确 kill 条件，避免后续 agent 重复消耗

## 5. 任务拆分模板（给其他 agent）

- **Agent A：结构探针**
  - 负责 cheap probes 和 kill 证据
- **Agent B：联合搜索**
  - 负责长跑 SA，定期输出 champion
- **Agent C：验证与落地**
  - 负责 full-32 + correctness gate + 回归测试
- **Agent D：知识沉淀**
  - 负责更新 `LESSONS.md` 与方向文档

每个 agent 的输出必须包含：
- 当前最优
- 与 seed 的对比
- 是否 landable
- 复现命令

## 6. 退出条件（防止无限跑）

满足任一条即可结束当前方向：
- N 次重启均未低于 best（如 4~8 restart）
- 结构探针证明为 sub-floor 吸收
- 新候选无法通过 PSPACE=0 或 correctness gate
- 已命中 LESSONS 中的禁止重试条款

## 7. 当前实验的可复用结论

- `offset + combine`：必须联合搜，单轴易 flat
- `d3 + d4`：强耦合，单独贪心不稳定
- `@1085`：tail 类 SA 接近收敛，sub-1000 需要结构性 deep-gather 方案
- 文档与证据链必须与代码同步提交，否则知识会蒸发

## 8. 配套文件

- 编排手册（tmux + Claude）：`directions/48-cursor-tmux-claude-orchestration.md`
- Slides 叙述稿：`directions/49-agentic-slides-narrative.md`
- 全史：`directions/46-wave7-1085-journey.md`
- 禁止重试：`directions/LESSONS.md`
- 关键工具：
  - `experiments/w7_oracle.py`
  - `experiments/anneal_genome_w8.py`
  - `experiments/anneal_joint_w7c.py`
  - `experiments/anneal_d3d4_joint.py`


# 面试 PPT 文字素材生成计划（2026-07）

## 0. 目标与受众

**受众**：面试官（不是老板）。关注点：

- 技术深度（架构选型理由、坑、解法）
- 问题解决思路（如何 debug、如何评估）
- Agent 项目中的不可替代价值（不是"调 API 搭工作流就完事"）

**策略**：以"我"为核心，深讲 1 个最具深度的 Agent 项目。**单一项目深讲 > 多个项目浅讲**。

## 1. 项目范围（已确认）

| # | 项目 | 角色 | 篇幅 |
|---|------|------|------|
| 1 | **WFXM Butler 框架** | Agent 平台本身（多工具 / 多项目 / 微信 / 记忆 / 调度） | 唯一深讲 |
| - | 灵文1号 novel-factory | （跳过，本次不讲） | — |
| - | DemoPilot | （跳过） | — |

**技术标签提案**（待你确认）：

> **"跨进程工具路由 + 多源记忆治理"**

候选备选（如果你觉得不准确）：
- "面向个人的微信原生 Agent 平台"
- "自研多项目多工具调度框架"
- "跨会话状态机 + 工具副作用治理"

## 2. 文件夹结构

```
projects/interview-ppt-2026-07/
├── README.md                  # 索引
├── 00-plan.md                 # 本计划
├── 01-wfxm-butler/            # 唯一深讲项目
│   ├── 01-situation-task.md   # S + T
│   ├── 02-action.md           # A：6 大技术细节
│   ├── 03-result.md           # R：量化 + Baseline 对比
│   ├── 04-learning.md         # L：反思
│   ├── 05-tech-tag.md         # 一句话技术标签
│   └── 06-architecture.mmd    # Mermaid 架构图（项目级）
├── diagrams/                  # 跨章节共用图
│   ├── wfxm-architecture.mmd  # 整体架构
│   ├── tool-routing.mmd       # 跨进程工具路由
│   ├── memory-system.mmd      # 多源记忆治理
│   ├── wechat-integration.mmd # 微信入口
│   └── runtime-jobs.mmd       # 调度 / runtime jobs
└── talking-points/            # 面试话术
    ├── 01-opening-pitch.md    # 30 秒开场白
    ├── 02-deep-dive-script.md # 2-3 分钟深讲口播稿
    ├── 03-common-qa.md        # 高频追问 Q&A
    └── 04-whiteboard-guide.md # 白板画法指南
```

## 3. 各文件内容大纲

### 01-situation-task.md（S + T，4 块必填）

1. **痛点真实性**：业务遇到了 XX 瓶颈（具体场景，**禁用"领导让我做"**）
2. **Agent 必要性**：为什么必须 Agent（推理 / 工具调用复杂度）
3. **你的 KPI**：可量化目标（准确率 / 时长 / 成本）
4. **你的角色**：0-1 架构 / 优化 / 模块 owner（**必须明确**）

### 02-action.md（A：6 大技术细节）

| # | 维度 | 关键问题 |
|---|------|----------|
| 1 | 架构范式 | ReAct / Plan-and-Execute / Multi-Agent 选型理由 |
| 2 | 框架与底层 | 自研 vs LangChain/AutoGen，含自研 vs 第三方踩坑对比 |
| 3 | 记忆机制 | 短期窗口 + 长期向量库（数据量 / 检索延迟） |
| 4 | 工具调用 | 工具数 + 幻觉处理 + 异常回退 |
| 5 | 提示词工程 | 得意 system prompt 结构 + Few-shot/Zero-shot |
| 6 | 难点攻克 | 最让你睡不着觉的 bug + 解决方案 |

### 03-result.md（R：硬指标）

- 效率：耗时、Token、TTFT
- 质量：成功率、人工干预率
- 对比：**vs Baseline（必填！）** — 例如 vs 直接 GPT-4 不带 Agent

### 04-learning.md（L：反思）

- 架构反思：过度设计 / 设计不足
- 评估之难：LLM-as-Judge vs 人工 / 评估本身缺陷
- 认知颠覆：对 LLM 能力边界的新认知

### 05-tech-tag.md

> "如果让我用一句话记住这个项目，它的最大技术挑战是【XX】。"

### 06-architecture.mmd

Mermaid 架构图（输入 → 规划 → 调用工具 → 观察 → 输出），重点突出"工具路由 + 记忆治理"

### diagrams/（5 个）

- `wfxm-architecture.mmd` — 一张总览图（面试开场用）
- `tool-routing.mmd` — 跨进程工具路由时序（深讲 1）
- `memory-system.mmd` — 多源记忆分层（深讲 2）
- `wechat-integration.mmd` — 微信→Agent→回复链路
- `runtime-jobs.mmd` — 调度系统（job / cron / drift）

### talking-points/

- 30 秒开场白（突出"一个项目、两大技术挑战：跨进程工具路由 + 多源记忆治理"）
- 2-3 分钟深讲口播稿（带节奏标注）
- 高频追问 Q&A（10-15 条）
- 白板画法指南（关键架构图怎么徒手画，30 秒搞定）

## 4. 生成顺序（依赖关系）

1. **Phase 1**：`01-wfxm-butler/01-situation-task.md`（先定调）
2. **Phase 2**：`01-wfxm-butler/02-action.md`（核心：6 大技术细节）
3. **Phase 3**：`01-wfxm-butler/03-result.md`（量化）
4. **Phase 4**：`01-wfxm-butler/04-learning.md` + `05-tech-tag.md`
5. **Phase 5**：`01-wfxm-butler/06-architecture.mmd` + `diagrams/`（5 张图）
6. **Phase 6**：`talking-points/`（4 个话术文件，依赖前面所有）

## 5. 关键决策点（待你确认）

- [ ] 技术标签是否同意 **"跨进程工具路由 + 多源记忆治理"**？或选备选？
- [ ] 是否需要中英双语？默认**全中文**（保留英文术语：Plan-and-Execute / Few-shot / ReAct / Drift）

## 6. 不做的事

- ❌ 不生成 .pptx 文件（用你现有工具转）
- ❌ 不直接生成演示文稿
- ✅ 只生成文字素材 + mermaid 源码
- ✅ mermaid 完成后用 `mmdc` 或在线工具转图嵌入 PPT

## 7. 工作流

每写完一个文件，我会停下来问你：

- 内容是否准确（你比我更了解细节）
- 哪些技术细节你想"润色成面试官爱听的话术"
- 是否有敏感信息要脱敏（公司名、客户名、内部代号）

## 8. 风险与注意事项

- **技术细节准确性**：基于 WFXM 当前代码状态，部分细节我可能过时，由你校对
- **量化数据**：R 栏必须有 Baseline 对比；如无准确数据，我会标 `⚠ 待你补充`
- **LangChain 等外部库**：用户工作区可能没用 LangChain，纯自研，我会按"自研"路线写
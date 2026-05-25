# MetaGPT ↔ Butler v4 对照分析报告

> **日期**：2026-05-25  
> **对照源**：`reference/MetaGPT`（本地 gitignore，不嵌入运行时）  
> **Butler 基线**：[`v4-architecture.md`](../architecture/v4-architecture.md)、[`reference-learning-plan-2026-05.md`](reference-learning-plan-2026-05.md)（P0–P2 已收口）  
> **合并路线图**：[`external-agent-reports-improvement-roadmap-2026-05.md`](external-agent-reports-improvement-roadmap-2026-05.md) **主线 N**、PR-X5  
> **产品边界**：[`four-reports-out-of-scope-2026-05.md`](four-reports-out-of-scope-2026-05.md) §2、[`five-reports-not-done-2026-05.md`](five-reports-not-done-2026-05.md) §1–§2  
> **原则**：只借鉴设计/理论，不引入 MetaGPT `Team`/`Environment` 全框架、不变成「软件公司」默认自治

---

## 1. 执行摘要

| 维度 | MetaGPT | Butler v4 |
|------|---------|-----------|
| 主场景 | 多角色「软件公司」：一行需求 → PRD/设计/代码/文档 | 微信远程管家 + 单会话 Agent Loop |
| 编排 | `Team` → `Environment` 轮询；Role 订阅 Action（SOP-as-code） | 用户触发 + `/workflow` YAML DAG + `delegate_task` |
| 记忆 | 按 `cause_by`（Action 类型）索引 + Chroma LTM | 会话 transcript + 压缩/剪枝 + 项目 `MEMORY.md` |
| 工具 | 大量 Python 工具 + BM25 召回 + LLM 排序 | ~9 核心工具 + 可选 MCP |
| 产物 | `ProjectRepo` 文档树（PRD/设计/任务/代码摘要） | `AgentReport`（微信摘要 + `/详细`） |
| 自治 | 预算驱动多轮、较长自主流水线 | 人工门控、无默认通宵自治 |

**MetaGPT 核心哲学**：`Code = SOP(Team)` — SOP 固化在 Role/Action 与文档仓库里。

**Butler 核心哲学**：生产级单 Loop + 可选 DAG；微信通道、上下文经济学、门控是主战场。

**结论**：

- **不是把 Butler 变成 MetaGPT**，而是有选择地借「多 Agent 协作 + 结构化产出 + 经验复用」中 Butler 尚未覆盖、且未在产品边界否决的能力。
- **Butler 已强、MetaGPT 难替代**：上下文与 Loop 卫生、微信线束、运行观测、DAG 真并行、工作流门控。
- **最值得提炼的 3 件事**：① `exp_cache` 式经验复用；② 工具 recall/rank；③ 结构化输出校验 + workflow checkpoint。
- **最不该做的 3 件事**：默认软件公司多角色自治、AFlow/SPO 全自动优化、全量 RoleZero 命令协议。

---

## 2. 架构对照

```mermaid
flowchart TB
  subgraph Butler["Butler v4"]
    WX[微信 Gateway] --> H[message_handler]
    H --> O[orchestrator]
    O --> L[agent_loop]
    L --> T[tools / delegate_task]
    WF[/workflow YAML/] --> TO[task_orchestrator]
    TO --> L
    HG[human_gate] -.-> WF
  end

  subgraph MetaGPT["MetaGPT"]
    U[User requirement] --> Team
    Team --> Env[Environment / MGXEnv]
    Env --> R1[TeamLeader]
    R1 --> R2[PM / Architect / Engineer]
    R2 --> PR[ProjectRepo 文档树]
    R2 --> Act[Action / ActionNode]
    Act --> Exp[@exp_cache]
  end
```

### 2.1 MetaGPT 核心模块（对照源路径）

| 领域 | 关键路径 | 设计要点 |
|------|----------|----------|
| Team / Role / Environment | `metagpt/team.py`、`environment/base_env.py`、`roles/role.py` | 多 Agent pub/sub；Role 私有 `msg_buffer`；`watch` 订阅上游 Action |
| SOP / Action | `metagpt/software_company.py`、`actions/*.py`、`actions/action_node.py` | 文档流水线：需求 → PRD → 设计 → 任务 → 代码 |
| 记忆 | `metagpt/memory/memory.py`、`memory/role_zero_memory.py` | 按 `cause_by` 索引；working + LTM；`memory_k` 截断 |
| Planner | `metagpt/strategy/planner.py`、`actions/di/write_plan.py` | Plan + AskReview + 代码执行反馈注入 |
| 经验池 | `metagpt/exp_pool/decorator.py`、`exp_pool/manager.py` | `@exp_cache`：检索 → 完美命中跳过 → 评分入库 |
| 项目仓库 | `metagpt/utils/project_repo.py` | Git + 固定文档目录语义（PRD/SD/Task/…） |
| 工具推荐 | `metagpt/tools/tool_recommend.py` | BM25 recall + LLM rank |
| 成本 | `metagpt/utils/cost_manager.py`、`team.py` | `Team.invest(budget)` 预算隐喻 |
| 输出修复 | `metagpt/utils/repair_llm_raw_output.py`、`actions/action_node.py` | 结构化 fill/review/revise 循环 |
| 增量开发 | `actions/write_code_plan_and_change_an.py`、CLI `--inc` | 文档 diff + git-diff 式变更计划 |
| 序列化 | `metagpt/team.py`、`schema.py` | Team/Role 崩溃恢复 |
| 研究扩展 | `metagpt/ext/aflow/`、`metagpt/ext/spo/` | 工作流/ prompt 搜索（非默认 CLI 路径） |

### 2.2 Butler 对应模块

| 领域 | 关键路径 | 设计要点 |
|------|----------|----------|
| Agent Loop | `butler/core/agent_loop.py` + 子模块 | 自建 ReAct；压缩/prune/failover/streaming |
| 编排 | `butler/orchestrator.py` | 系统提示、Skill、模型、Loop 工厂 |
| DAG 多 Agent | `butler/task_orchestrator.py` | 拓扑排序 + 分层并行；子 Loop 全控 |
| 工作流 | `butler/workflows/` | YAML steps + 变量池 + builtin |
| 人工门控 | `butler/human_gate.py` | 微信确认；批准后需重发 `/workflow` |
| Gateway | `butler/gateway/message_handler.py` 等 | 队列、会话、出站 |
| 报告 | `butler/report.py` | `AgentReport` + 渐进披露 |
| 实验 | `butler/experiments/` | ledger.tsv + experiment mode |

---

## 3. Butler 已强、MetaGPT 难替代的部分

以下不必从 MetaGPT 搬迁，应继续深化现有实现：

| 能力 | Butler 模块 | MetaGPT 差距 |
|------|-------------|--------------|
| 上下文与 Loop 卫生 | `context_pipeline`、`tool_prune_policy`、`reactive_compact`、`streaming_tools` | 主要靠 `memory_k` + LTM，无 reactive compact |
| 微信线束 | `message_queue`、`session_registry`、`outbound_bridge`、`steer` | 无 WeChat / 入站队列 |
| 运行观测 | `runtime_metrics` + `/诊断` | 有 CostManager，无 Gateway 级指标 |
| DAG 真并行 | `task_orchestrator.execute_graph()` | Environment 轮询，非 Butler 式子 Loop 继承 |
| 工作流门控 | `human_gate` + `requires_approval` | 有 AskReview，无微信重发约束 |

已有 YAML 工作流示例（接近 MetaGPT dev→review SOP，更轻）：

- `butler/workflows/builtin/dev-qa-loop.yaml` — implement → qa（PASS/FAIL）
- `butler/workflows/builtin/ui-dev-qa-loop.yaml`、`novel-factory.yaml`、`ops-checklist.yaml`

---

## 4. MetaGPT 可提炼能力（按优先级）

### 4.1 P0 — 高价值、与 Butler 边界一致

#### 4.1.1 经验池（Experience Pool）— 降成本、稳输出

**MetaGPT**：`@exp_cache` 对 LLM 调用做「检索 → 完美命中则跳过 → 否则执行并评分入库」。

- 源：`metagpt/exp_pool/decorator.py`、`exp_pool/manager.py`
- 开关：`config.exp_pool.enabled` / `enable_read` / `enable_write`
- 用于：`ActionNode.fill()`、`RoleZero.llm_cached_aask()`

**Butler 现状**：`experiments/ledger.tsv` 记指标；`outcomes.py` 注入 prompt；无「同 prompt 模式命中缓存」。

**建议落地**（零/轻依赖）：

| 项 | 说明 |
|----|------|
| 挂载点 | `butler/transport/auxiliary_client.py` 或压缩摘要路径 |
| 机制 | prompt 指纹 + BM25/精确匹配（不必 Chroma） |
| 标签 | `workflow_step` / `tool_name` / `compress_summary` |
| 存储 | `.butler/experiences/`，与 `BUTLER_EXPERIMENT_MODE` 共用目录 |
| 默认 | 只读缓存；写入需显式 `BUTLER_*` 开关 |

**边界**：五报告 S7 否决「全自动 APE/ToT prompt 搜索」；经验池是缓存 + 质量门，不是 prompt 进化，不冲突。

---

#### 4.1.2 工具两阶段推荐（Recall + Rank）

**MetaGPT**：BM25 召回 + LLM 选 top-k，不全量 schema 进 context。

- 源：`metagpt/tools/tool_recommend.py`
- 流程：recall（BM25/embedding）→ rank（LLM）→ 注入选中工具 schema

**Butler 现状**：`skills_list` / `skill_view` 已降 Skill token；核心工具 ~9 个；**MCP 开启后** schema 会膨胀。

**建议落地**：

| 项 | 说明 |
|----|------|
| 挂载点 | `butler/tools/registry.py` 或 orchestrator 建 loop 前 |
| 范围 | MCP + 可选 `terminal` |
| 实现 | BM25 over tool description（`rank_bm25` 或轻量自研） |
| 互补 | 与 `BUTLER_SCHEMA_OPTIMIZE` 配合：减 schema 体积 + 减暴露工具数 |

对应五报告 P2「ToolsEngine manifest」子集，不必做完整 manifest 合并。

---

#### 4.1.3 结构化输出管线（ActionNode 思想）

**MetaGPT**：`ActionNode` — 生成 → 自动/人工 review → revise，挂钩 `exp_cache`。

- 源：`metagpt/actions/action_node.py`、`utils/repair_llm_raw_output.py`

**Butler 现状**：workflow 有 `output_schema`；`butler/report.py` 的 `parse_structured_output` 只做 JSON 抽取；**无 Pydantic 校验与失败重试**（五报告 P2 主线 I 未排期）。

**建议落地**：

| 项 | 说明 |
|----|------|
| 挂载点 | `enrich_output_schema` 之后 |
| 行为 | schema 校验 + 单次 LLM 修复（借鉴 REVIEW_TEMPLATE，不引入 ActionNode 树） |
| 优先 | workflow 终步、`delegate_task` 的 `output_format=json` |
| 微信 | 校验失败 → 简短 FAIL + 重试一次 |

---

#### 4.1.4 项目文档仓库（ProjectRepo 子集）

**MetaGPT**：固定目录语义管理 SOP 产物（PRD、system_design、task、code_summary…）。

- 源：`metagpt/utils/project_repo.py`

**Butler 现状**：`DESIGN.md`、`MEMORY.md`、workflow 变量 `{{step.output}}`；无 PRD → 设计 → 任务清单标准路径。

**建议落地**（产品可选）：

| 项 | 说明 |
|----|------|
| 路径 | `.butler/artifacts/` 下 3–5 个固定文件名（如 `REQUIREMENTS.md`、`TASKS.md`） |
| 写入 | workflow builtin，非 Python Action 类 |
| 注入 | `post_compact_cleanup` / orchestrator 只索引路径 + 摘要 |
| 合并 | 与 `design_md_sections.py` 协调，避免第二套 DESIGN 体系 |

---

### 4.2 P1 — 中等价值、需控范围

#### 4.2.1 按 Action 类型的记忆索引（cause_by）

**MetaGPT**：`Memory` 按 `cause_by` 检索。

**Butler 建议**：`session_transcript.jsonl` 增加 `source: tool|compact|workflow_step|delegate`；压缩时优先保留 patch/delegate/workflow 相关行（升级现有 `tool_prune_policy` 为语义标签）。

**不做**：Chroma Worker（S1）、TradingAgents checkpoint（S9）。

---

#### 4.2.2 Planner + 计划状态注入

**MetaGPT**：`Planner` + `get_plan_status()` 把已完成任务与代码结果写回 prompt。

**Butler 建议**：`task_orchestrator` 维护 `PlanSnapshot`（goal + steps + status）；`dev-qa-loop` 扩展 FAIL → 自动重跑 implement（`max_retries` 已有，缺结构化 replan）。

**不做**：无用户消息也跑满 Team 的自主分解。

---

#### 4.2.3 增量开发（--inc 文档 diff）

**MetaGPT**：`--inc` + `write_code_plan_and_change_an` 生成类 git diff 变更说明。

**Butler 建议**：builtin `incremental-patch.yaml`；输出 `.butler/artifacts/CHANGE_PLAN.md`；复用 `read_state` + `patch`。

**不做**：`graph_repo` / class view（过重）。

---

#### 4.2.4 团队级序列化 / 崩溃恢复

**MetaGPT**：`Team.serialize()` + `recover_path` CLI。

**Butler 建议**：长跑 workflow 每步写 `.butler/workflow_runs/<id>.json`（步骤状态 + 变量池 + 最后 `AgentReport`）；transcript 取证，workflow checkpoint 可恢复 DAG。

**仍不做**：批准后自动下一步（`reference-learning-plan` 已否决 auto-resume workflow）。

---

#### 4.2.5 成本 / Token 预算

**MetaGPT**：`Team.invest(budget)`，每轮检查 `total_cost >= max_budget`。

**Butler 建议**：`runtime_metrics` 增加会话级 token 预算（与 `turn_token_budget` 互补）；接近预算时压缩 + 微信提示。

---

### 4.3 P2 — 研究向 / 与产品边界冲突

| MetaGPT 能力 | 建议 | Butler 文档依据 |
|--------------|------|-----------------|
| 全量多角色 `software_company` 默认跑通 | 不搬 | S8 否决固定 LangGraph |
| MGXEnv TeamLeader 中枢路由 | 仅借鉴「路由层」概念 | orchestrator 轻量任务分类 → workflow |
| AFlow / SPO prompt 工作流搜索 | 不搬 | S7 否决 ToT/APE |
| RoleZero 命令 JSON + 全工具表 | 不搬 | 与 Butler tool_calls 重复 |
| 浏览器 / Playwright 工具链 | 不搬 | four-reports-out-of-scope |
| 内置 Jupyter `ExecuteNbCode` | 不搬 | 与受限 `terminal` 冲突 |
| 全量 MCP Host | 不搬 | S11 |

---

## 5. MetaGPT 有、Butler 无（MetaGPT 侧清单）

便于反向理解边界，**非 Butler 缺口清单**：

- WeChat / 消息网关、入站队列、出站 bridge
- Reactive context compaction（413、hygiene preflight、post-compact 锚点）
- MCP Host（MetaGPT 为进程内 Python 工具注册）
- `workflow_steps` 权限 + 微信 human_gate
- runtime metrics / doom-loop 检测（CC 线束概念）
- 单 Agent Loop 默认路径（MetaGPT 总是多 Role Environment）
- 入站 jsonl WAL

---

## 6. 与 Butler 已有规划的对照

### 6.1 五报告 P2 未排期 ↔ MetaGPT

| P2 项（`five-reports-not-done` §2） | MetaGPT 对应 | 提炼方式 |
|-------------------------------------|--------------|----------|
| Pydantic 终局校验 | ActionNode fill/review | 仅 workflow/delegate 终局 |
| Reflexion 长期 experience | exp_pool + LTM | 轻量 exp_cache，不用 Chroma Worker |
| Prompt eval 闭环 | SPO（ext） | 语料 + rubric，不做全自动搜索 |
| ToolsEngine manifest | ToolRecommender + registry | BM25 recall + 白名单 |

### 6.2 reference-learning-plan 已收口

已落地：Prometheus 指标、OpenClaw 队列语义、session 生命周期、Dify DAG + HITL → `task_orchestrator` + `human_gate`。

**未导入**：Dify/OpenClaw 运行时、Kafka、jsonl queue WAL、workflow auto-resume。

MetaGPT 的 `watch` / `cause_by` 订阅可作为 workflow 条件边（`when: implement.status == FAIL`）的远期增强，非短期必做。

---

## 7. 推荐实施路线图（若立项）

### 阶段 A（1–2 周，低风险）

1. Workflow checkpoint JSON（§4.2.4）
2. `output_schema` + Pydantic 校验与一次修复（§4.1.3）
3. 会话 token 预算指标（§4.2.5）

### 阶段 B（2–4 周，降本增效）

4. 轻量 `exp_cache`（§4.1.1）
5. MCP 工具 BM25 召回（§4.1.2）
6. transcript / 剪枝语义标签（§4.2.1）

### 阶段 C（产品可选）

7. `.butler/artifacts/` 文档 SOP 模板 + builtin workflow（§4.1.4、§4.2.3）
8. `PlanSnapshot` + FAIL 自动回滚 implement（§4.2.2）

每项立项前须查：`four-reports-out-of-scope-2026-05.md` §2、`five-reports-not-done-2026-05.md` §1。

---

## 8. 对照矩阵（速查）

| 维度 | Butler v4（强） | 相对 MetaGPT 缺口 |
|------|-----------------|-------------------|
| Runtime 控制 | 自建 Loop、压缩、failover | — |
| Channel | 微信 Gateway、队列、门控 | 无 IDE/桌面 Team UI |
| Multi-agent | DAG + `delegate_task` | 无默认 PM/Architect/Engineer 编制 |
| SOP | YAML workflow + handoff | 无文档-SOP 链（PRD→设计→任务） |
| Coordination | 依赖 context + 变量池 | 无 pub/sub、共享 env、Role watch 网 |
| Autonomy | 人工门控 | MetaGPT 更长自主流水线 |
| Artifacts | `AgentReport` + 文件变更 | 无标准化 SOP 文档类型 |
| Validation | 文本 PASS/FAIL、decision 正则 | 无 Pydantic 重试管线（P2） |
| 经验复用 | ledger + outcomes | 无 exp_cache |
| Scale | 单进程 Gateway | 无分布式 Agent 池 |

---

## 9. 总结

MetaGPT 适合作为 **「多 Agent + 结构化文档 + 经验缓存」** 的参考实现库。Butler 应保持 **单 Loop 生产内核**，把 MetaGPT 的 SOP **降解**为：

- YAML workflow
- 固定 artifact 路径（`.butler/artifacts/`）
- 可选 exp_cache / 工具 recall 层

而不是引入 `Team` / `Environment` 全框架或默认「软件公司」自治模式。

---

## 10. 维护

- 若落地 §7 任一项：同步 [`v4-architecture.md`](../architecture/v4-architecture.md)、[`config/reference.md`](../config/reference.md)（新增 `BUTLER_*` 时）
- 新否决项：写入 [`five-reports-not-done-2026-05.md`](five-reports-not-done-2026-05.md) §1
- 完成 P2：从该文档 §2 删除并在 [`five-reports-improvement-roadmap-2026-05.md`](five-reports-improvement-roadmap-2026-05.md) §9 标 ✅

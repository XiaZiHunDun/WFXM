# Butler v4 与 Hermes-Agent 对比与可提炼报告

> **日期**：2026-05-25（**勘误**：2026-05-25，对照 Butler 代码与 `reference/hermes-agent` 实测修订）  
> **对照源**：`reference/hermes-agent`（Nous Research Hermes Agent，本地 gitignore）  
> **Butler 基线**：[`v4-architecture.md`](v4-architecture.md)、[`hermes-extraction-map.md`](hermes-extraction-map.md)  
> **相关规划**：[`cc-butler-gap-analysis-2026-05.md`](../plans/active/cc-butler-gap-analysis-2026-05.md)、[`reference-learning-plan-2026-05.md`](../plans/archive/reference-learning-plan-2026-05.md)

---

## 1. 执行摘要

Butler v4 已从 Hermes **模块化提炼**大量运行时能力（压缩、并行工具、中断、Gateway 队列、委派策略等），并**刻意不** import `AIAgent`、不移植 `run_agent.py` / `gateway/run.py` 单体。

本报告结论：

1. **不必重复造轮子**：已落地项见 [`hermes-extraction-map.md`](hermes-extraction-map.md)。  
2. **Butler 相对 Hermes 的保留优势**：多项目记忆、DAG workflow + human_gate、`AgentReport` 微信 UX、CC 线束 P0–P4。  
3. **仍可提炼的高价值项**（按优先级）：流式记忆 scrub、Gateway 流式出站桥、freshness 门控 auto-continue、**补齐** slash 旁路清单与入队顺序、危险命令检测、transcript 检索、子 Agent 独立迭代预算；`execute_code` PTC 仅作可选长期项且需独立安全评审。  
4. **明确不移植**：单体 Loop、20+ 平台网关、70+ 工具生态、完整 Hermes SessionDB 替代 Butler 记忆模型。

---

## 2. 总体定位差异

| 维度 | Hermes-Agent | Butler v4 |
|------|--------------|-----------|
| 核心循环 | 单体 `AIAgent`（`run_agent.py` ~15.4k 行 / ~790KB） | 模块化 `butler/core/agent_loop.py`（编排 ~580 行）+ 子模块 |
| 网关 | 30+ 平台适配、`GatewayRunner`（`gateway/run.py` ~16k 行） | **仅微信 iLink**（`butler/gateway/platforms/wechat_ilink.py`） |
| 工具集 | 70+ 工具模块、MCP Host、浏览器、沙箱、`execute_code` | **~28** 内置/扩展工具（`get_tool_definitions`）+ 可选 MCP **薄客户端**（非 Host） |
| 记忆 | 文件 + 可插拔外部 Provider + SQLite FTS5 会话库 | 多项目 `MEMORY.md` + `semantic_index` + turn 围栏 |
| 编排 | `delegate_task` 子 Agent + cron + skills | `delegate_task` + **DAG `run_workflow`** + **human_gate** |
| 产品场景 | 通用多平台 Agent | **微信管家 + 多项目** |

### 2.1 架构示意（简化）

```text
Hermes:
  gateway/run.py → AIAgent (run_agent.py) → tools/registry (70+)
                    → MemoryManager + SessionDB (FTS5)

Butler v4:
  gateway/message_handler.py → agent_loop.py → tools/registry (~28 + opt. MCP)
                               → ButlerMemory + semantic_index
  gateway/message_queue (steer / interrupt / collect / followup)
```

> Hermes 行号（如 `run_agent.py` L7166+）仅作阅读锚点，随上游版本漂移，不作 API 契约。

### 2.2 Hermes 关键入口（阅读对照用）

| 场景 | Hermes 路径 |
|------|-------------|
| Agent 主循环 | `reference/hermes-agent/run_agent.py` |
| Gateway | `reference/hermes-agent/gateway/run.py` |
| 流式出站 | `reference/hermes-agent/gateway/stream_consumer.py` |
| 上下文压缩 | `reference/hermes-agent/agent/context_compressor.py` |
| 记忆编排 | `reference/hermes-agent/agent/memory_manager.py` |
| 危险命令批准 | `reference/hermes-agent/tools/approval.py` |
| PTC / execute_code | `reference/hermes-agent/tools/code_execution_tool.py` |
| 会话 DB | `reference/hermes-agent/hermes_state.py` |
| 内部文档 | `reference/hermes-agent/website/docs/developer-guide/architecture.md` |

---

## 3. 已提炼内容（不必重复实现）

完整对照表见 [`hermes-extraction-map.md`](hermes-extraction-map.md)。摘要如下：

| 类别 | Butler 模块 | Hermes 参考 | 状态 |
|------|-------------|-------------|------|
| 主循环编排 | `butler/core/agent_loop.py` | `run_agent.py` 片段 | ✅ |
| 工具批次 | `butler/core/tool_batch.py` | 同左 | ✅ |
| LLM 重试 | `butler/core/llm_retry.py` | 同左 | ✅ |
| 上下文管线 | `butler/core/context_pipeline.py` | 同左 | ✅ |
| 五阶段压缩 | `butler/core/context_compressor.py` | `agent/context_compressor.py` | ✅ |
| 压缩防劫持前缀 | `SUMMARY_PREFIX` | 同左 | ✅ |
| 并行工具 | `butler/core/parallel_tools.py` | `run_agent.py` 并行批 | ✅ |
| 可中断 API | `butler/transport/interruptible_client.py` | L7166+ | ✅ |
| Steer | `butler/core/steer.py` | L5180+ | ✅ |
| Failover / 错误分类 | `butler/transport/fallback.py` 等 | 同左 | ✅ |
| Gateway 队列 | `butler/gateway/message_queue.py` | Gateway 队列语义 | ✅ |
| 委派策略 | `butler/delegate_policy.py` | `delegate_tool.py` | ✅ |
| Cache-safe 委派 | `butler/core/cache_safe_delegate.py` | 子 loop 前缀对齐 | ✅ |
| 记忆 turn 围栏 | `butler/session_lifecycle.py` | `<memory-context>` | ✅ |
| 轻量 Hooks | `butler/gateway/hooks.py` | plugins 子集 | ✅ |

### 3.1 明确不移植（hermes-extraction-map 约定）

| Hermes 路径 | 原因 |
|-------------|------|
| `run_agent.py` (~790KB) | 违背 v4 自建 Loop |
| `gateway/run.py` (~16k 行) | 微信由 `wechat_ilink.py` 原生实现 |
| 50+ 工具 / MCP Host / 浏览器 | 超出 Butler 产品边界 |
| `hermes_state.SessionDB` 全量替代 | 与多项目记忆模型重复 |
| 完整 Plugin 平台 | 强依赖 Hermes 全局状态 |

---

## 4. Butler 相对 Hermes 的既有优势（保留项）

1. **多项目记忆与 Skill 路由**（`butler/orchestrator.py`、`butler/skills/router.py`）  
2. **DAG 工作流 + 步骤级工具白名单 + 人工门控**（`butler/workflows/runner.py`、`butler/human_gate.py`）  
3. **结构化 `AgentReport` + 微信 `/详细` 渐进披露**（`butler/report.py`）  
4. **CC 线束 P0–P4 已落地**（见 [`cc-butler-gap-analysis-2026-05.md`](../plans/active/cc-butler-gap-analysis-2026-05.md) §4–§11）  
5. **记忆注入围栏文案**（`inject_turn_memory` / `_render_turn_memory_context`）

---

## 5. 仍可提炼的能力（按优先级）

### 5.1 P0 — 高收益、与微信长会话强相关

#### 5.1.1 流式记忆围栏清洗（`StreamingContextScrubber`）

| 项 | 说明 |
|----|------|
| **Hermes** | `agent/memory_manager.py`：`StreamingContextScrubber` 状态机，跨 chunk 剔除 `<memory-context>…</memory-context>` |
| **Butler 现状** | 有 turn 级围栏；CLI 有 `think_scrubber` / `content_sanitize`；**无** memory-context 流式 scrub |
| **建议** | 新增 `StreamingMemoryContextScrubber`，接入 `LoopCallbacks.on_stream_delta` |
| **落点** | `butler/transport/` 或 `butler/session_lifecycle.py` |
| **收益** | 防止记忆块泄漏到流式 UI/微信 |

#### 5.1.2 Gateway 流式出站桥（`GatewayStreamConsumer` 模式）

| 项 | 说明 |
|----|------|
| **Hermes** | `gateway/stream_consumer.py`：sync callback → `queue.Queue` → asyncio 限速编辑；工具边界 `_NEW_SEGMENT` |
| **Butler 现状** | `outbound_bridge.py` 仅 typing + ack + 里程碑；`message_handler` **未**接 `on_stream_delta` |
| **建议** | 验证微信 iLink 是否支持消息编辑后，移植 **sync→async 队列 + 限速** 骨架（不必搬全文件） |
| **收益** | 长回复渐进可见，降低「只有 typing」焦虑 |

#### 5.1.3 Freshness 门控的 auto-continue

| 项 | 说明 |
|----|------|
| **Hermes** | `gateway/session.py`：`resume_pending` + 时间窗（约 1h），避免陈旧 transcript 误续跑 |
| **Butler 现状** | 有 interrupt、队列 interrupt、`compaction_checkpoint`；**无** freshness 续跑 |
| **建议** | `session_transcript` + `last_active_at`；`BUTLER_AUTO_CONTINUE_MAX_AGE` 控制 |
| **收益** | 工具批中断后减少手动重述 |

#### 5.1.4 双层 Gateway 守卫 + 审批类 slash 旁路（补齐，非从零）

| 项 | 说明 |
|----|------|
| **Hermes** | 普通消息入队 interrupt；`/approve`、`/stop` 等 **绕过** 后台 Agent 任务 |
| **Butler 现状** | **已部分实现**：`handle_message` 在 `enqueue_inbound` 之前处理 `terminal_approval`、`human_gate`；`_is_sessionless_command` 含 `/approve`、`/queue`、`/steer` 等，走 slash 路径不进队。仍有缺口：与 Hermes 对齐的 **完整 slash 清单**（如 `/stop` 与运行中 loop 的严格优先）、队列满/长任务时的竞态 |
| **建议** | 在 `message_handler` **补齐**入队前短路表并写回归测试；勿重复实现已有 human_gate / terminal approve 路径 |
| **收益** | 「确认」与队列控制类指令不被长队列阻塞 |

---

### 5.2 P1 — 中等收益、需控范围

#### 5.2.1 危险命令检测 + 可选智能批准

| 项 | 说明 |
|----|------|
| **Hermes** | `tools/approval.py`：模式库、按 `session_key` 的 `contextvars` 审批上下文、辅助 LLM auto-approve |
| **Butler 现状** | `permissions.yaml` + terminal argv allowlist + `terminal_approval`；`execution_context` 等已有 `ContextVar`，但 **终端批准路径未**按 session 绑定 Hermes 式审批键；**无**内容模式库、**无** LLM 分类器 |
| **建议** | 先移植模式检测 + 在 `terminal_approval` 绑定 `session_key`；`BUTLER_TERMINAL_SMART_APPROVE` 默认关 |
| **注意** | 与 `BUTLER_ENABLE_TERMINAL=0` 默认策略一致 |

#### 5.2.2 跨会话 transcript 检索

| 项 | 说明 |
|----|------|
| **Hermes** | `hermes_state.py` FTS5 + `session_search` 工具 |
| **Butler 现状** | `session_transcript.jsonl`；`butler_memory` FTS5 偏跨项目经验 |
| **建议** | sqlite3 stdlib 或 ripgrep 封装 `search_transcript` 工具 |
| **收益** | 长对话内「上周说过什么」可检索 |

#### 5.2.3 子 Agent 独立迭代预算

| 项 | 说明 |
|----|------|
| **Hermes** | `IterationBudget`：父子独立计数，子默认 50 |
| **Butler 现状** | `iteration_budget.py` 已移除未接线；仅靠 `delegate_policy` 深度 |
| **建议** | 仅为 `delegate_task` / `run_workflow` 恢复独立 `max_iterations` 上限 |
| **收益** | 防止子 Agent 吃光父轮次 |

#### 5.2.4 压缩摘要模板增强（Hermes context_compressor v2）

| 项 | 说明 |
|----|------|
| **Hermes** | Resolved/Pending、「Remaining Work」、迭代摘要合并、按比例 budget |
| **Butler 现状** | 已有 `SUMMARY_PREFIX` |
| **建议** | 对齐 summarizer **prompt 模板**（改 prompt + fixture，不动架构） |
| **参考** | `reference/hermes-agent/agent/context_compressor.py` |

---

### 5.3 P2 — 高收益但成本高 / 需产品决策

| 能力 | Hermes 参考 | 建议 |
|------|-------------|------|
| **execute_code / PTC** | `tools/code_execution_tool.py` | 独立沙箱子模块；env scrub + 工具白名单；**须安全评审**；勿直接开放任意代码执行 |
| **插件 Hook 扩展** | `hermes_cli/plugins.py` 20+ hooks | 按需求逐个增加 hook 点，不复制完整 Plugin 平台 |
| **MCP Server** | `mcp_serve.py` | 仅当有 IDE 调 Butler 会话需求；见 `butler-mcp-capability-2026-05.md` |
| **Cron = 完整 Agent** | `cron/scheduler.py` | 若 runtime job 仅脚本，可学「定时 Agent turn + 出站 + 注入扫描」 |

---

### 5.4 P3 — 低优先级或明确不做

| Hermes 能力 | 不建议原因 |
|-------------|------------|
| 整包 `run_agent.py` / `gateway/run.py` | 违背 v4 架构约束 |
| 70+ 工具 / 浏览器 / 多终端后端 | 超出产品边界 |
| 20+ 消息平台 | 仅做微信 |
| 完整 SessionDB 替代 Butler 记忆 | 模型重复 |
| Skills Hub / 自动写 skill | 已有 Skill 路由 |
| Kanban 看板 | 已有 workflow DAG |

---

## 6. 与 Claude Code 差距的互补关系

[`cc-butler-gap-analysis-2026-05.md`](../plans/active/cc-butler-gap-analysis-2026-05.md) 主对照 Claude Code；Hermes 可补 **另一类** 缺口：

| CC / Butler 缺口 | Hermes 可补 |
|------------------|-------------|
| 权限 LLM 分类器 | `approval.py` 智能批准（可选） |
| 会话持久化 / 检索 | FTS5 `session_search` |
| 流式出站 UX | `GatewayStreamConsumer` |
| Token 经济学极端场景 | `execute_code` PTC |
| Gateway 并发安全 | `approval.py` 按 session 的审批 `contextvars`（Butler 有 `ContextVar` 基础设施，终端批准未对齐） |

CC 已对齐项（micro prune、spill、read_state、queue、cache-safe delegate）**不必**再从 Hermes 重复实现。

---

## 7. 建议落地路线图

```text
阶段 A（1–2 周，小 diff）
  → StreamingMemoryContextScrubber（CLI + 未来 Gateway 流式）
  → 补齐 slash 旁路清单与测试（在现有 terminal/human_gate/sessionless 路径上扩展）
  → terminal_approval 按 session_key 绑定 ContextVar（并发批准如有竞态）

阶段 B（2–4 周）
  → transcript FTS 或 search_transcript 工具
  → freshness auto-continue（BUTLER_AUTO_CONTINUE_MAX_AGE）
  → delegate 独立 iteration 上限
  → context_compressor 摘要 prompt 对齐 Hermes v2

阶段 C（产品拍板后）
  → 微信渐进式流式回复（需 iLink API 能力验证）
  → 危险命令模式库 + 可选 smart approve
  → execute_code 沙箱（独立安全评审）

明确不做：Hermes 单体 Loop、多平台网关、全量工具体系
```

### 7.1 阶段 A 建议改动文件

| 任务 | 建议路径 |
|------|----------|
| 流式 memory scrub | `butler/transport/memory_context_scrubber.py`（新）、`butler/core/llm_retry.py` |
| slash 旁路补齐 | `butler/gateway/message_handler.py`（扩 `_is_sessionless_command` / 入队前表） |
| 批准 session ContextVar | `butler/tools/terminal_approval.py`（或 `permission_approvals.py`） |

---

## 8. 结论

- Hermes 对 Butler 的**剩余价值**集中在：**网关流式桥、流式记忆 scrub、会话检索、审批/危险命令、中断续跑、子 Agent 预算**；应以 **小模块** 迁入 `butler/core` / `butler/gateway`，而非恢复 `AIAgent`。  
- Butler **不必**向 Hermes 看齐：多平台、大工具集、单体 Loop、外部记忆 Provider 市场。  
- **优先 P0**：流式 scrub、（API 允许时）Gateway 流式桥、auto-continue freshness、slash 旁路 **补齐** — 直接改善微信长会话体验（批准/门控已有部分旁路，见 §5.1.4）。

---

## 9. 文档维护

若落地本报告 P0/P1 项并新增 `BUTLER_*` 开关，请同步：

- [`v4-architecture.md`](v4-architecture.md)
- [`hermes-extraction-map.md`](hermes-extraction-map.md)（新增行）
- [`docs/config/reference.md`](../config/reference.md)、`.env.example`

---

*初稿：Cursor Agent 对话分析归档，2026-05-25。勘误：对照仓库代码与 Hermes 参考树实测修订（工具数量、slash 旁路现状、contextvars 表述）。*

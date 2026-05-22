# Butler v4 架构文档

## 架构概述

Butler v4 采用**自建 Agent Loop + 模块化复用**方案 — Butler 完全控制自己的 Agent Loop，
不再 import Hermes AIAgent。Transport / 工具 / Loop 均在 `butler/` 内自建。  
**微信网关**：`butler gateway` 为 Butler 原生 iLink + `ButlerMessageHandler`（无 Hermes 子进程，不支持其它平台）。详见 [`hermes-decoupling.md`](hermes-decoupling.md)。

```
用户 ─→ CLI / 微信（Gateway）
         │
         ▼
   Butler Orchestrator          ← 分层配置、记忆注入、Skill 路由
         │
         ▼
   Butler Agent Loop (自建)     ← 编排入口 agent_loop.py (~300 行)
         │
         ├─→ context_pipeline   ← 压缩 / hygiene / API 消息准备
         ├─→ llm_retry          ← LLM 重试、schema 恢复、failover
         ├─→ tool_batch         ← 工具批次（顺序/并行、guardrails、envelope）
         ├─→ parallel_tools     ← 并行批调度与路径冲突检测
         ├─→ Transport Layer    ← 独立的 LLM 协议转换（chat_completions / anthropic）
         ├─→ Tool Registry      ← Butler 自建工具系统 + 审计观测
         ├─→ Task Orchestrator  ← DAG 多 Agent 编排（真并行）
         └─→ Report Pipeline    ← 结构化报告 + 渐进披露
```

## 核心架构变更（v3 → v4）

| 维度 | v3 | v4 |
|------|----|----|
| Agent Loop | Hermes AIAgent (import) | Butler 自建（编排 298 行 + 子模块 628 行）|
| LLM 调用 | 通过 AIAgent.run_conversation | 通过 LLMClient + Transport |
| 工具系统 | Hermes 50+ 工具 | Butler 自建 9 核心工具 |
| 子 Agent | Hermes delegate_task (绕过 Butler) | Butler 编排器全控 |
| 编排控制力 | 低（只能通过 prompt/hook 间接影响）| 完全（每一步可插手）|
| Hermes 升级风险 | 高（依赖内部 API）| Loop + 微信 Gateway 均已 Butler 原生 |
| 信息回传 | 占位/无压缩 | AgentReport 全链路（`/详细`、缓存）；会话压缩回传为二期可选 |

## 核心模块

### Butler Core（Loop 栈 ~926 行，2026-05-20 实测）

| 模块 | 路径 | 说明 |
|------|------|------|
| Agent Loop（编排） | `butler/core/agent_loop.py` | 主循环、`LoopResult`、fallback 切换、对外 API |
| 上下文管线 | `butler/core/context_pipeline.py` | `ContextPipeline`：压缩摘要、hygiene preflight、API 前 repair/sanitize |
| LLM 重试 | `butler/core/llm_retry.py` | `call_llm_with_retry`：空内容重试、schema 降级、压缩回退、中断 |
| 工具批次 | `butler/core/tool_batch.py` | `process_tool_calls`、tool envelope、guardrails 接线、顺序中断补全 |
| 并行工具批 | `butler/core/parallel_tools.py` | 安全并行执行、`precheck_tool`（interrupt/halt 跳过） |
| Loop 类型 | `butler/core/loop_types.py` | `LoopConfig` / `LoopCallbacks` / `LoopResult` / `LoopStatus` |
| Orchestrator | `butler/orchestrator.py` | 系统提示注入、模型配置、Skill 路由、AgentLoop 工厂 |
| Task Orchestrator | `butler/task_orchestrator.py` | DAG 拓扑排序、真并行（asyncio.to_thread）、委派深度、session 审计归属 |
| Gateway Session | `butler/gateway/session_registry.py` | 按 `session_key` 管理 Loop 生命周期与 health；驱逐时清理工具审计 |

### Transport Layer (~800 行)

| 模块 | 路径 | 说明 |
|------|------|------|
| 类型定义 | `butler/transport/types.py` | NormalizedResponse, ToolCall, Usage |
| 抽象基类 | `butler/transport/base.py` | ProviderTransport ABC |
| Chat Completions | `butler/transport/chat_completions.py` | OpenAI 兼容协议 |
| Anthropic | `butler/transport/anthropic_transport.py` | Anthropic / MiniMax 协议 |
| Provider 注册 | `butler/transport/providers.py` | 9 家主流厂商配置 |
| LLM Client | `butler/transport/llm_client.py` | 实际 HTTP 调用、流式/非流式 |

### 工具系统 (~500 行)

| 工具 | 说明 |
|------|------|
| `read_file` | 文件读取（行号标注、偏移/限制）|
| `write_file` | 文件写入/创建 |
| `patch` | 精确字符串替换 |
| `terminal` | 受限命令执行（默认关闭；需 `BUTLER_ENABLE_TERMINAL=1`，仅 allowlist argv，不支持 shell 管道/重定向）|
| `search_files` | 基于 ripgrep 的全文搜索 |
| `list_directory` | 目录列表 |
| `skills_list` | Skill 元数据索引（降 token）|
| `skill_view` | 按需加载 Skill 全文 |
| `delegate_task` | 委派任务给项目级 Agent（深度限制 + 隔离历史）|

### Hermes 提炼层（模块化复用）

从 `reference/hermes-agent` 提炼的运行时机制，**不** import `AIAgent`：

| 模块 | 说明 |
|------|------|
| `butler/core/context_compressor.py` | 五阶段上下文压缩（工具裁剪、头尾保护、LLM 摘要）|
| `butler/core/message_repair.py` | API 前消息序列修复 |
| `butler/core/parallel_tools.py` | 安全并行工具批（含 halt/interrupt `precheck_tool`）|
| `butler/core/tool_batch.py` | 工具批次执行与 JSON envelope _finalize |
| `butler/core/llm_retry.py` | LLM 调用重试与 schema 恢复 |
| `butler/core/context_pipeline.py` | 上下文压缩与 Gateway hygiene |
| `butler/core/hygiene_preflight.py` | 长会话 85% token / 消息数预检压缩 |
| `butler/core/schema_recovery.py` | 工具 schema `pattern`/`format` 剥离后重试 |
| `butler/core/retry_policy.py` | 重试退避策略 |
| `butler/gateway/session_registry.py` | Gateway 多会话 Loop 注册与 LRU/idle 驱逐 |
| `butler/transport/error_classifier.py` | API 错误分类 |
| `butler/transport/fallback.py` | Provider failover 链 |
| `butler/transport/auxiliary_client.py` | 压缩/post-session 辅助模型 |
| `butler/tool_guardrails.py` | 工具循环检测与阻断 |
| `butler/delegate_policy.py` | 委派深度与阻断工具 |
| `butler/session_lifecycle.py` | 会话边界记忆提交 |
| `butler/gateway/hooks.py` | 轻量 HookBus |
| `butler/skills/guard.py` | Skill 静态安全扫描 |
| `butler/transport/content_sanitize.py` | 国产模型 think/XML 输出清洗 |
| `butler/core/message_sanitize.py` | API 前消息卫生（stub tool、thinking-only）|
| `butler/core/tool_call_normalize.py` | 工具去重、名称修复、delegate 上限 |
| `butler/transport/interruptible_client.py` | 可中断 LLM 调用 + stale 超时 |
| `butler/core/steer.py` | 运行中用户指引（`/steer`）|
| `butler/core/delegate_context.py` | 委派子 Agent 回调透传 |

完整对照见 [`hermes-extraction-map.md`](hermes-extraction-map.md)。

### Agent Loop 数据流（模块化）

```
用户消息 → sanitize_surrogates (agent_loop)
    → 主循环 (agent_loop):
        prepare (context_pipeline):
            compress_context → repair_message_sequence → sanitize_api → drop_thinking_only
            → 可选 pre_llm_transform
        LLM (llm_retry + interruptible_client):
            complete/stream → sanitize_response
            → 空内容重试 / schema 恢复 / 压缩回退 / failover
        工具 (tool_batch + parallel_tools):
            assistant tool_calls 消息
            → guardrails before/after → dispatch (registry envelope)
            → 并行: execute_tools_parallel + precheck_tool(halt/interrupt)
            → 顺序: 中断/halt 后为剩余 call 补齐 tool 消息
            → apply_steer
        截断续写 (agent_loop + loop_response)
    → LoopResult (+ diagnostics / tool 审计按 session_key)
```

### Gateway 观测（`/health`）

- 轮次诊断：压缩、schema 降级、Skill/记忆同步等写入 `health_by_session`
- 工具审计：内存 deque 按 `session_key` 分桶；`/new`、session 驱逐与 registry `on_session_removed` 同步清理
- 无轮次 health 快照时，仍展示当前 session 的工具调用/失败/错误码摘要

### Gateway 层

| 模块 | 路径 | 说明 |
|------|------|------|
| 消息处理 | `butler/gateway/message_handler.py` | 平台消息→Butler Pipeline→格式化响应 |
| 平台适配 | `gateway/platforms/wechat_ilink.py` | 仅微信 iLink（个人助手） |

### 产品层（保留自 v3）

| 模块 | 路径 | 说明 |
|------|------|------|
| Agent 角色 | `butler/agent_profiles.py` | dev/content/review 三角色 |
| 分层记忆 | `butler/memory/` | ButlerMemory + ProjectMemory |
| Skill 系统 | `butler/skills/` | 加载/路由/自动合并 |
| 结构化报告 | `butler/report.py` | AgentReport + 渐进披露（/detail）|
| 后处理 | `butler/post_session.py` | 会话结束时记忆/技能提炼 |

## Agent Loop 设计

Butler v4 的 Agent Loop 是系统的核心——完全自建，不依赖任何外部 agent 框架。  
**`agent_loop.py` 仅保留编排**；压缩、重试、工具批次等逻辑在独立模块中，便于单测与演进。

```python
while not done and iterations < budget:
    1. ContextPipeline.prepare_messages_for_api()
    2. call_llm_with_retry()  # Transport + 重试/failover
    3. 解析响应：
       a. 纯文本 → 截断续写或完成
       b. 工具调用 → process_tool_calls() → Tool Registry
       c. 失败/中断 → LoopStatus + 审计事件
    4. callbacks（iteration / LLM / tool）
```

模块化约束（见 [`hermes-extraction-map.md`](hermes-extraction-map.md)）：
- `agent_loop.py` 保持 **< 400 行**（当前 ~300 行，编排为主）
- 新增能力优先落入 `tool_batch` / `llm_retry` / `context_pipeline` 等子模块，避免回灌单体文件

核心价值：**Butler 完全控制每一步**：
- 上下文管线可独立测试压缩与 hygiene
- LLM 重试层统一 schema 恢复与 failover
- 工具批次层统一 envelope、guardrails、并行 halt 提前终止
- Gateway 层按 session 隔离 Loop、health 与审计

## 解决的设计痛点

| 痛点 | v3 状态 | v4 状态 |
|------|---------|---------|
| delegate_task 绕过 Butler | ❌ Hermes 控制 | ✅ Butler 全控 |
| 信息回传压缩 | ❌ 未实现 | ✅ AgentReport 结构化链路；跨轮压缩摘要见 context_pipeline（非 delegate 回传） |
| 子 Agent 模型配置 | ❌ 不经过 Butler | ✅ AgentSpawnConfig |
| 子 Agent 工具集控制 | ❌ 缺失 | ✅ 可按角色过滤 |
| 会话隔离 | ❌ CLI 用进程内列表 | ✅ Gateway 按 session_key |
| Hermes 版本依赖风险 | ❌ 依赖内部 API | ✅ 零 Hermes import / 无子进程 |
| 结构化报告 + /detail | ❌ 占位返回 | ✅ 完整实现 |
| 工具审计 / `/health` | ❌ 无 | ✅ session 分桶 + 生命周期对齐 |
| Agent Loop 可维护性 | ❌ 单体 ~500+ 行 | ✅ 编排 + 4 个子模块拆分 |

## 测试覆盖

**pytest 全绿**（默认排除 `live_llm`；CI 见 `.github/workflows/ci.yml`），覆盖：
- Transport 层（types、registry、chat_completions、anthropic、retry_utils）
- Provider 注册表（列表、查询、别名解析）
- Agent Loop 栈（`test_agent_loop.py`、`test_tool_batch.py`、`test_context_pipeline.py`）
- 工具系统（定义、dispatch、路径安全、envelope、审计）
- Tool guardrails（线程安全、warn JSON、halt/block）
- Orchestrator（系统提示、客户端创建、循环创建）
- Task Orchestrator（DAG、委派深度、execution_context / 审计 session）
- Gateway（`test_gateway_handler.py`、`test_gateway_session_registry.py`、hygiene）
- Report / CLI / Session lifecycle
- 真实 API smoke（可选）：`BUTLER_RUN_REAL_API_SMOKE=1 pytest -m live_llm tests/test_real_api_smoke.py`

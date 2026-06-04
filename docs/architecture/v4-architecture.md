# Butler v4 架构文档

> **更新**：2026-05-26（全面审查修正行数/工具数/路径；CC §11 P3/P4 + **外部对标 P0–P2** 已收口，见 [`plans/reference-learning-plan-2026-05.md`](../plans/archive/reference-learning-plan-2026-05.md)）  
> **对照**：[`plans/cc-butler-gap-analysis-2026-05.md`](../plans/active/cc-butler-gap-analysis-2026-05.md) · 规划索引 [`plans/README.md`](../plans/README.md) · 环境变量 [`config/reference.md`](../config/reference.md)

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
   Butler Agent Loop (自建)     ← 编排入口 agent_loop.py (~780 行)
         │
         ├─→ context_pipeline   ← 压缩 / hygiene / 分级剪枝 / post-compact 锚点
         ├─→ llm_retry          ← LLM 重试、schema 恢复、failover、流式 on_tool_call_ready
         ├─→ tool_batch         ← 工具批次（spill 落盘、prefetch、guardrails、envelope）
         ├─→ parallel_tools     ← 并行批调度与路径冲突检测
         ├─→ streaming_tools    ← 流式只读工具参数完整后预执行（P2）
         ├─→ Transport Layer    ← 独立的 LLM 协议转换（chat_completions / anthropic）
         ├─→ Tool Registry      ← Butler 自建工具系统 + 审计观测
         ├─→ Task Orchestrator  ← DAG 多 Agent 编排（真并行）
         └─→ Report Pipeline    ← 结构化报告 + 渐进披露
```

## 核心架构变更（v3 → v4）

| 维度 | v3 | v4 |
|------|----|----|
| Agent Loop | Hermes AIAgent (import) | Butler 自建（编排 ~807 行 + 子模块 ~2117 行）|
| LLM 调用 | 通过 AIAgent.run_conversation | 通过 LLMClient + Transport |
| 工具系统 | Hermes 50+ 工具 | Butler 自建 9 核心 + 多项可选工具 |
| 子 Agent | Hermes delegate_task (绕过 Butler) | Butler 编排器全控 |
| 编排控制力 | 低（只能通过 prompt/hook 间接影响）| 完全（每一步可插手）|
| Hermes 升级风险 | 高（依赖内部 API）| Loop + 微信 Gateway 均已 Butler 原生 |
| 信息回传 | 占位/无压缩 | AgentReport 全链路（`/详细`、缓存）；会话压缩回传为二期可选 |

## 核心模块

### Butler Core（Loop 栈 ~2924 行，2026-05-31 实测）

| 模块 | 路径 | 说明 |
|------|------|------|
| Agent Loop（编排） | `butler/core/agent_loop.py` (~807 行) | 主循环、`LoopResult`、fallback 切换、对外 API |
| 上下文管线 | `butler/core/context_pipeline.py` | `ContextPipeline`：压缩摘要、hygiene preflight、API 前 repair/sanitize |
| LLM 重试 | `butler/core/llm_retry.py` | `call_llm_with_retry`：空内容重试、schema 降级、压缩回退、中断 |
| 工具批次 | `butler/core/tool_batch.py` | `process_tool_calls`、tool envelope、guardrails 接线、顺序中断补全 |
| 并行工具批 | `butler/core/parallel_tools.py` | 安全并行执行、`precheck_tool`（interrupt/halt 跳过） |
| Loop 类型 | `butler/core/loop_types.py` | `LoopConfig` / `LoopCallbacks` / `LoopResult` / `LoopStatus` |
| Orchestrator | `butler/orchestrator.py` | 系统提示注入、模型配置、Skill 路由、AgentLoop 工厂 |
| Task Orchestrator | `butler/task_orchestrator.py` | DAG 拓扑排序、真并行（asyncio.to_thread）、委派深度、session 审计归属 |
| Gateway Session | `butler/gateway/session_registry.py` | 按 `session_key` 管理 Loop 生命周期与 health；驱逐时清理工具审计 |
| 工具结果落盘 | `butler/core/tool_result_storage.py` | 单条 spill + **单轮聚合预算**（`enforce_message_tool_budget`）+ 按工具阈值 |
| 会话 transcript | `butler/core/session_transcript.py` | `transcript.jsonl`（user/assistant/compact/queue/spill 指针） |
| Reactive compact | `butler/core/reactive_compact.py` | 413 时按 API round 丢弃旧轮再压缩 |
| 项目权限规则 | `butler/permissions.py` | `.butler/permissions.yaml` allow/deny/ask |
| 分级剪枝 | `butler/core/tool_prune_policy.py` | read/grep 等可清空旧结果；patch/delegate 保留更长摘要 |
| 压缩后锚点 | `butler/core/post_compact_cleanup.py` | LLM 摘要后重注入 MEMORY / 任务 / Skill / AGENTS·DESIGN 节锚点 |
| 实验账本 | `butler/experiments/ledger.py` | `.butler/experiments.tsv`；runtime 解析 `METRIC`；`/诊断` 最近行 |
| 研究模式 | `butler/experiments/mode.py` | `BUTLER_EXPERIMENT_MODE=1` 时 harness 只读、`experiments/` 可写 |
| DESIGN 节提取 | `butler/core/design_md_sections.py` | `DESIGN.md` frontmatter / Do's-Don'ts / responsive；post-compact 与 orchestrator 摘要 |
| Markdown 切块 | `butler/memory/chunking.py` | 标题树切块；`reindex` 可选启用 |
| 检索子 query | `butler/memory/query_decompose.py` | `BUTLER_RAG_SUBQUERY=1` 启发式多路召回合并 |
| Observation Store | `butler/memory/observer_queue.py` + `observation_store.py` | PostToolUse 按 workspace 入队、workspace `.butler/observations.db`、`content_hash` 轻量去重、TTL/row retention、PreRead 路径历史 |
| RAG 诊断 | `butler/ops/rag_diagnostics.py` | 空召回 fallback、检索指标写入 `/诊断` |
| 工具隐式上下文 | `butler/tools/tool_implicit_context.py` | `BUTLER_TOOL_IMPLICIT_CONTEXT` |
| Schema 预优化 | `butler/core/schema_optimizer.py` | `BUTLER_SCHEMA_OPTIMIZE` |
| 读后再改 | `butler/core/read_state.py` | `read_file` 记录 mtime；`patch`/`write_file` 校验 |
| 循环可观测 | `butler/core/loop_types.py` | `LoopTransitionReason` → `/诊断`、completion 遥测 |
| Cache-safe 委派 | `butler/core/cache_safe_delegate.py` | 子 Agent 共享父 system 静态前缀（prompt cache 对齐） |
| 流式只读预取 | `butler/core/streaming_tools.py` | 流式 tool 参数 JSON 完整即 dispatch，结果进 `_tool_prefetch` |
| Turn token 预算 | `butler/core/turn_token_budget.py` | `+500k` / `/budget` 提高单轮 `max_iterations` |

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

**9 核心工具**（始终注册）：

| 工具 | 说明 |
|------|------|
| `read_file` | 文件读取（行号标注、偏移/限制）|
| `write_file` | 文件写入/创建 |
| `patch` | 精确字符串替换 |
| `search_files` | 基于 ripgrep 的全文搜索 |
| `list_directory` | 目录列表 |
| `skills_list` | Skill 元数据索引（降 token）|
| `skill_view` | 按需加载 Skill 全文 |
| `delegate_task` | 委派任务给项目级 Agent（深度限制 + 隔离历史）|
| `run_workflow` | DAG 工作流触发 |

**可选工具**（按配置启用）：

| 工具 | 启用条件 |
|------|----------|
| `terminal` | `BUTLER_ENABLE_TERMINAL=1`（受限 argv + allowlist）|
| `ask_clarification` | `BUTLER_ASK_CLARIFICATION=1`（默认开启）|
| `search_project_knowledge` | 项目知识库检索 |
| `session_todos_list` / `session_todos_write` | `BUTLER_SESSION_TODOS=1` |
| `git_status` / `git_diff` / `git_log` / `git_branch` | `BUTLER_ENABLE_GIT=1` |
| `git_add` / `git_commit` | `BUTLER_ENABLE_GIT_WRITE=1` |
| `download_file` | `BUTLER_ENABLE_DOWNLOAD=1` |
| `web_fetch` | `BUTLER_ENABLE_WEB_FETCH=1` |
| `execute_code` | `BUTLER_EXECUTE_CODE=1`（须安全评审）|
| `mcp_*` | `BUTLER_MCP_ENABLED=1` + `butler-system[mcp]` |

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
| `butler/core/delegate_context.py` | 委派子 Agent 回调 + 父 `system_prompt` 透传 |
| `butler/core/tool_result_storage.py` | 大工具结果 spill（P0） |
| `butler/core/tool_prune_policy.py` | 按工具名分级 micro 剪枝（P0） |
| `butler/core/post_compact_cleanup.py` | 压缩后锚点重注入（P0） |
| `butler/core/read_state.py` | read-before-edit + mtime（P0） |
| `butler/core/streaming_tools.py` | 流式只读工具预取（P2） |
| `butler/core/cache_safe_delegate.py` | 委派 system + tools/messages 指纹（P2/v2） |
| `butler/core/session_transcript.py` | JSONL 取证与恢复子集（P3） |
| `butler/core/reactive_compact.py` | 413 reactive 局部压缩（P4） |
| `butler/permissions.py` | 声明式工具权限（P4） |
| `butler/gateway/message_queue.py` | 入站 now/next/later 队列（P1） |
| `butler/core/turn_token_budget.py` | 单轮迭代预算扩展（P1） |

完整对照见 [`hermes-extraction-map.md`](hermes-extraction-map.md)。CC 差距落地见 [`cc-butler-gap-analysis-2026-05.md`](../plans/active/cc-butler-gap-analysis-2026-05.md)。

### 上下文经济学与 Gateway 控制（P0–P2）

```text
每轮 API 前（context_pipeline）:
  preemptive_compact（LLM 前估算 → compact / truncate / overflow_fail）
  → tool_prune_policy（分级 micro）→ 阈值内才 LLM compress → post_compact 锚点（含 AGENTS.md / DESIGN.md 节）

工具结果（tool_batch）:
  maybe_spill_tool_result → 消息内指针；read_file 读回全文

编辑安全（registry + read_state）:
  patch / write_file(已有文件) ← 须先 read_file 且 mtime 未变

Gateway（message_handler + queue_settings）:
  reply_admission 单飞 → 忙则入队；bot_loop_guard（可选）；Owner `/批准执行` terminal 绑定
  忙会话非斜杠 → message_queue（now/next/later；mode: followup|collect|interrupt|steer）
  collect → pop_all_merged；interrupt → loop.interrupt()
  会话 `/queue` 覆盖 → `.butler/gateway_queue/*.json`
  轮次结束 drain；主回复已发 + bridge → schedule_supplementary_reply
  Stop hook exit 2 / decision:block → stop_hook_blocked
  human_gate：`requires_approval` 步骤 → 微信「确认」→ 再发 `/workflow`

委派（registry delegate_task）:
  get_parent_system_prompt → apply_cache_safe_system_prompt → 子 AgentLoop

流式（llm_client + agent_loop）:
  on_tool_call_ready → 只读工具预取 → process_tool_calls(prefetched)
```

### Hook 总线（Shell + In-Process）

Butler 同时跑两套 Hook 总线：**Shell 钩子**（`butler/hooks/runner.py`，CC 兼容，`~/.butler/hooks.yaml` 配）和 **In-Process 钩子**（`butler/gateway/hooks.py`，轻量 Python 字典注册）。两套并行不冲突，按场景选用。

#### 系统对照

| 维度 | Shell 钩子 | In-Process 钩子 |
|---|---|---|
| 入口 | `butler/hooks/runner.py` | `butler/gateway/hooks.py` |
| 配置 | `~/.butler/hooks.yaml` / `<project>/.butler/hooks.yaml` | `register_hook(name, fn)` 在代码内注册 |
| 延迟 | 子进程 + JSON stdin/stdout | 进程内函数调用，零延迟 |
| 典型用途 | 审计、通知、外部副作用（git status、metric 推送） | 上下文注入、改写、轻量决策（`pre_llm_call` 加临时上下文） |
| 阻塞语义 | exit code 2 = 阻塞；其他非零 = warn | try/except 永吞（不阻塞）；返回 `{"action": "skip"}` 等可显式阻断 |
| 上下文化 | `hookSpecificOutput.additionalContext` JSON 字段 | 返回值直接 list[str] 拼入 |

#### 主流 Hook 点

| 名称 | 类型 | 触发时机 | 阻塞方式 |
|---|---|---|---|
| `UserPromptSubmit` | Shell | 每个 LLM turn 入口，用户 prompt 入栈后 | exit 2 |
| `pre_llm_call` | In-Process | `apply_pre_llm_context()`，注入临时上下文 | 返回值追加，不阻断 |
| `pre_gateway_dispatch` | In-Process | 消息分发前，文本改写/跳过 | `{"action": "skip"}` 跳；`{"action": "rewrite", "text": ...}` 改写 |
| `PreToolUse` (= `pre_tool_execute`) | Shell | 工具执行前，按 `matcher` 匹配 | exit 2（或 `BUTLER_HOOK_FAIL_CLOSED=1` 下任何非零） |
| `PostToolUse` / `PostToolUseFailure` | Shell | 工具执行后 | 不阻塞；stderr / context 拼到 tool 结果 |
| `PreCompact` + `pre_compact` | **双调用** | 压缩前 | Shell exit 2 阻断；In-Process 注入事实抽取 |
| `PostCompact` + `post_compact` | **双调用** | 压缩后 | Shell 返回 contexts；In-Process 注入锚点 |
| `PermissionDenied` | Shell | 权限拒绝后 | `{"retry": true}` 触发重试 |
| `SessionStart` / `SessionEnd` | Shell | 会话开始/结束 | 不阻塞（仅审计） |
| `Stop` | Shell | turn 完成 | exit 2 标记 `stop_hook_blocked` |
| `SubagentStart` / `SubagentStop` | Shell | 委派子 agent 启停 | 不阻塞（仅审计） |

#### 触发顺序（一次完整 turn）

```
[消息入] → sanitize → UserPromptSubmit (shell)
       → pre_gateway_dispatch (in-proc, 可改写)
       → pre_llm_call (in-proc, 追加上下文)
       → LLM call
       → 工具循环:
            PreToolUse (shell, matcher 匹配)
              → tool exec
              → PostToolUse (shell)
       → [若触发压缩]:
            PreCompact (shell)  →  pre_compact (in-proc, 事实抽取)
              → compress()
              → PostCompact (shell, 返回 additionalContext)
              → post_compact (in-proc, 锚点注入)
       → Stop (shell)
```

#### 失败统一契约

- **Shell** exit code：
  - `0` / `None` = pass
  - `2` = block，stderr（或 stdout）作为 block reason（截 2000 字）
  - 其他非零 = warn，logger 记录不阻断
  - `BUTLER_HOOK_FAIL_CLOSED=1` 时 PreToolUse 走"任何非零即阻断"严格模式
- **In-Process**：`try/except Exception` 全部吞，logger.warning 一行后继续；显式 `action: skip/rewrite` 或返回 `block_message` 才算阻断

#### 双调用约定（压缩钩子）

`butler/core/compaction_task.py:64-90` 和 `:147-173` 串行触发两套钩子：
1. **先 Shell**（`run_pre_compact_hooks` / `run_post_compact_hooks`）—— exit 2 立即阻断压缩；返回的 `additionalContext` 拼入下一轮 prompt
2. **后 In-Process**（`invoke_hook("pre_compact" | "post_compact", ...)`）—— 事实抽取 / 锚点注入

顺序选择理由：Shell 是**有副作用**的外部命令（git 状态、metric 推送），先跑能在压缩取消时省下 In-Process 工作；In-Process 是**纯函数**的事实抽取，放后面更稳。两套都 try/except 隔离，单点失败不互相影响。

#### 配置参考

- Shell 钩子样例：`butler/hooks/hooks.yaml.example`（含 11 种事件各一例）
- In-Process 注册 API：`butler.gateway.hooks.register_hook(name, fn)`；调用 `invoke_hook(name, **kwargs)`
- PreCompact payload：`{"hook_event_name": "PreCompact", "estimated_tokens", "message_count", "iteration", "session_key"}`
- PreToolUse payload：`{"hook_event_name": "PreToolUse", "tool_name", "tool_input"}`

### Agent Loop 数据流（模块化）

```
用户消息 → sanitize_surrogates (agent_loop)
    → 主循环 (agent_loop):
        prepare (context_pipeline):
            tool_prune（分级）→ compress_context（阈值门控）→ post_compact 锚点
            → repair_message_sequence → sanitize_api → drop_thinking_only
        LLM (llm_retry + interruptible_client):
            complete/stream → sanitize_response
            → 流式: on_tool_call_ready 预取只读工具（streaming_tools）
            → 空内容重试 / schema 恢复 / 压缩回退 / failover
        工具 (tool_batch + parallel_tools):
            assistant tool_calls 消息
            → 复用 prefetched / spill 大结果 / read_state（写工具）
            → guardrails before/after → dispatch (registry envelope)
            → 并行: execute_tools_parallel + precheck_tool(halt/interrupt)
            → 顺序: 中断/halt 后为剩余 call 补齐 tool 消息
            → apply_steer
        截断续写 (agent_loop + loop_response)
    → LoopResult (+ transition_reason + diagnostics / tool 审计按 session_key)
```

### Gateway 入站与出站（微信）

```text
handle_message
  ├─ 会话忙 + 非斜杠 → enqueue（优先级 + BUTLER_GATEWAY_QUEUE_MODE）
  │     collect 合并 drain；interrupt 打断当前轮；steer 走 /steer
  ├─ UserPromptSubmit / 规划 / hygiene / turn_token_budget
  ├─ AgentLoop.run → 主回复
  └─ drain（BUTLER_GATEWAY_QUEUE_DRAIN_PER_TURN）
        ├─ bridge 可用且主回复非空 → schedule_supplementary_reply（第二条微信）
        └─ 否则 → 拼入主回复（--- 分隔）
完成推送（与主回复独立）: delegate / turn / workflow / timeout → schedule_completion_push
人工门控: workflow 步骤 requires_approval → 等待确认 → 用户再发 /workflow 续跑
```

### Gateway 观测（`/health` / `/诊断`）

- 轮次诊断：压缩、schema 降级、Skill/记忆同步等写入 `health_by_session`
- **运行指标**（外部对标 P0）：`butler/ops/runtime_metrics.py` — Counter/Gauge/Histogram 内存聚合；`completion_telemetry` / `hooks/telemetry` 统一写入；阈值见 [`ops/diagnostic-thresholds.md`](../ops/diagnostic-thresholds.md)
- 工具审计：内存 deque 按 `session_key` 分桶；`/new`、session 驱逐与 registry `on_session_removed` 同步清理
- 无轮次 health 快照时，仍展示当前 session 的工具调用/失败/错误码摘要

### Gateway 层

| 模块 | 路径 | 说明 |
|------|------|------|
| 消息处理 | `butler/gateway/message_handler.py` | 入站队列、斜杠、Loop 轮次、drain、health |
| 入站队列 | `butler/gateway/message_queue.py` | 忙会话排队；collect 合并；轮次结束 drain |
| 队列策略 | `butler/gateway/queue_settings.py` | mode/cap/drop；会话 `/queue` 覆盖 |
| 人工门控 | `butler/human_gate.py` | workflow 步骤需微信确认 |
| 运行指标 | `butler/ops/runtime_metrics.py` | 零依赖 Prometheus 风格快照 → `/诊断` |
| 出站桥 | `butler/gateway/outbound_bridge.py` | typing、progress ack、completion、supplementary |
| 完成推送 | `butler/gateway/completion_notify.py` | 委派/整轮/工作流额外消息 + 冷却 |
| Durable Outbox | `butler/gateway/durable_outbox.py` | completion push 发送前落盘、sent/failed 归档、本地 crash-safe 留痕 |
| Session | `butler/gateway/session_registry.py` | Loop 实例、active 标记、LRU 驱逐 |
| 平台适配 | `butler/gateway/platforms/wechat_ilink.py` | 仅微信 iLink（个人助手） |

### 依赖分层与本地状态原则

Butler v4 对“外部依赖引入”采用 **少量、分层、可选** 策略：

1. **core 默认最小化**：`pyproject.toml` `[project.dependencies]` 只保留主循环、transport、配置、YAML、HTTP、CLI、SQLite 等主路径必需依赖。  
2. **适配层走 optional extra**：微信、MCP、OCR、voice、PTY 等放在 `[project.optional-dependencies]`，按入口启用，不把 IDE/平台型能力拉进 core。  
3. **文件 / JSONL 是事实源**：`transcript.jsonl`、`MEMORY.md`、runtime task JSON、Gateway durable outbox 是主状态；SQLite 仅作为 **派生索引/查询层**（如 `observations.db`），不替换 transcript。  
4. **拒绝平台型重依赖**：不引入 Redis / Postgres / 向量库主存储 / LangGraph / Effect / Electron / 全量 MCP Host 来重塑 Butler 主航道。

### 产品层（保留自 v3）

| 模块 | 路径 | 说明 |
|------|------|------|
| Agent 角色 | `butler/agent_profiles.py` | dev/content/review 三角色 |
| 分层记忆 | `butler/memory/` | ButlerMemory + ProjectMemory |
| Observation 派生层 | `butler/memory/observer_queue.py`、`butler/memory/observation_store.py` | PostToolUse observation queue + SQLite 派生存储（不替换 transcript / MEMORY SSOT） |
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
- `agent_loop.py` 当前 ~807 行（含编排 + Loop 内各阶段的调度逻辑）
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
| 长会话 token / 编辑安全 | ❌ 统一截断 | ✅ spill + 分级剪枝 + read_state（P0） |
| 微信长轮次并发入站 | ❌ 仅 steer | ✅ 优先级队列 + mode/cap + drain 出站（CC P1 + 外部对标 P1） |
| 流式延迟 / 委派 cache | ❌ 批后工具 | ✅ streaming_tools + cache_safe_delegate（CC P2） |
| `/诊断` 运行指标 | ❌ 零散计数 | ✅ `runtime_metrics` 统一（外部对标 P0） |
| Workflow 步骤权限 | ❌ 全局工具表 | ✅ `workflow_steps` + `human_gate`（外部对标 P2） |

### 外部对标落地（2026-05，已收口）

与 **CC 线束** 独立；详见 [`reference-learning-plan-2026-05.md`](../plans/archive/reference-learning-plan-2026-05.md)。**不做**：入站队列 jsonl WAL、多实例 MQ。已做（opt-in）：确认后自动续跑 workflow（`BUTLER_WORKFLOW_AUTO_RESUME=1`）。

| 项 | 模块 | 微信命令 / 配置 |
|----|------|-----------------|
| P0 可观测 | `ops/runtime_metrics.py` | `/诊断` 运行指标；[`ops/diagnostic-thresholds.md`](../ops/diagnostic-thresholds.md) |
| P1 入站队列 | `gateway/queue_settings.py` + `message_queue.py` | `/queue`；`BUTLER_GATEWAY_QUEUE_*` |
| P2 工作流门控 | `human_gate.py` + `permissions.yaml` `workflow_steps` | `/确认` `/取消`；再发 `/workflow` |

### 体验增强落地（2026-05，P2）

| 项 | 模块 | 微信命令 / 配置 |
|----|------|-----------------|
| 多项目总览 | `gateway/message_handler._build_project_overview` | `/总览`、`/overview` |
| 项目级持久待办 | `tools/project_todos.py` | `/项目待办`；`<workspace>/.butler/todos.json` |
| Terminal 管道支持 | `tools/path_safety.py` pipe 段验证 | `BUTLER_TERMINAL_PIPE=1`；白名单命令间 `\|`，最多 5 段 |
| 首次使用引导 | `gateway/message_handler._maybe_welcome_prefix` | `BUTLER_ONBOARDING_WELCOME=1` |
| Workflow 确认自动续跑 | `human_gate._auto_resume_workflow` | `BUTLER_WORKFLOW_AUTO_RESUME=1` |

守门：`pytest tests/test_p2_remaining_features.py -q`

### 编排质量增强（2026-05）

| 项 | 模块 | 配置 |
|----|------|------|
| Cron 重复提醒 | `tools/reminder.py` | `set_reminder` when 支持 `每天 9:00`、`工作日`、cron 表达式 |
| 个人备忘录 | `tools/memo.py` | `BUTLER_MEMO_ENABLED=1`；tenant 级跨项目，5 工具（add/list/search/update/delete），`/备忘` 斜杠命令 |
| 通讯录 | `tools/contacts.py` | `BUTLER_CONTACTS_ENABLED=1`；tenant 级跨项目，5 工具（add/find/update/delete/list），`/通讯录` 斜杠命令 |
| 记账 | `tools/expense.py` | `BUTLER_EXPENSE_ENABLED=1`；tenant 级跨项目，4 工具（add/summary/list/delete），`/记账` 斜杠命令 |
| 习惯打卡 | `tools/habits.py` | `BUTLER_HABITS_ENABLED=1`；tenant 级跨项目，5 工具（create/checkin/stats/list/delete），`/打卡` 斜杠命令 |
| 向量检索层 | `memory/vector_store.py` | `[vectors]` extra（ChromaDB 优先，fallback 内存暴力搜） |
| Skill/工具语义路由 | `skills/router.py`、`core/tool_selector.py` | `BUTLER_SKILL_SEMANTIC_ROUTING`、`BUTLER_TOOL_SEMANTIC_SELECT`（需非 hashing embedder） |
| MCP 自助安装 | `tools/mcp_self_service.py` | `BUTLER_MCP_SELF_SERVICE=1`；`mcp_catalog_search`、`mcp_install`、`mcp_remove` |
| 压缩前 Fact 提取 | `core/fact_extraction.py` → `post_compact_cleanup.py` | `BUTLER_FACT_EXTRACTION=1`（默认开）；压缩后注入事实锚点 |
| Skill preferred_tools | `skills/router.py` → `core/skill_tool_bridge.py` → `core/tool_selector.py` | Skill frontmatter `preferred_tools` 字段保留工具不被筛掉 |

守门：`pytest tests/test_orchestration_improvements.py -q`

### OpenCode 对标落地（2026-05，P0–P2）

详见 [`plans/opencode-learning-plan-2026-05.md`](../plans/comparisons/opencode-learning-plan-2026-05.md)。

| 项 | 模块 |
|----|------|
| 压缩模板 / backward prune | `compaction_prompt.py`、`tool_output_prune.py` |
| last-match 权限 / doom loop | `permissions.py`、`tool_guardrails.py` |
| cache 计入用量 | `context_budget.record_usage_in_diagnostics` |
| 委派子代理 | `delegate_subagent_permissions.py`；`child_session_key` in `task_store` |
| 读文件规则注入 | `instruction_walkup.py` |
| P2 transcript / post-commit / todos | `session_transcript`、`post_commit.py`、`session_todos.py` |
| P2 hook mutate | `gateway/hooks.trigger_hooks_mutating` |

### 四报告增量（2026-05）

> 对照四份外部报告合并路线图；**不做项**见 [`plans/four-reports-out-of-scope-2026-05.md`](../plans/decisions/four-reports-out-of-scope-2026-05.md)；运维速查 [`guides/four-reports-capabilities-2026-05.md`](../guides/four-reports-capabilities-2026-05.md)。

| 主线 | 要点 |
|------|------|
| A 检索 | `semantic_index` fallback、`chunking` + `reindex`、`knowledge_search` 结构化引用、`query_decompose`、`butler memory search --verbose` |
| B Loop | `loop_budget_nudge`、compaction `IN-PROGRESS`、`inject_once`、`batch_sequence_guard` |
| C DESIGN | `design_md_sections`、`design_preset`、`ui-build`、`ui-dev-qa-loop`、租户 `design-system` skill 种子 |
| D 实验 | `experiments/ledger`、`mode`、`crash_guard`；`butler experiment *` CLI；`software-research` 模板 |
| E 支撑 | `tool_modes`、workflow 工具交、`tool_implicit_context`、`schema_optimizer`、`token_cost_diagnostics` |

守门：`pytest tests/test_ragflow_p0_retrieval.py tests/test_design_md_sections.py tests/test_experiment_ledger.py tests/test_query_decompose.py tests/test_support_line_e.py -q`

### 全面改进 Sprint 1–6（2026-05-29）

> 基于 10 份审查报告约 80 项问题，6 Sprint 全部落地。

| Sprint | 主题 | 要点 |
|--------|------|------|
| S1 安全/可靠性 | 原子写入 5 处、write_file/patch 二次确认、Human Gate TOCTOU 锁、ExecPolicy fail-closed、符号链接检测、Permissions 审计日志、Session Key 验证、Observation TTL 90d |
| S2 可观测性 | logger.debug→warning 16 处、exc_info 9 处、Gateway 错误分类 5 类、error_cards 接入、`/诊断` 增运行错误计数与 context metrics |
| S3 UX | `command_registry` 集中注册、帮助体系补全 ~15 命令、Welcome 默认启用、项目切换失败提示改善、处理中 ETA 反馈 |
| S4 架构/性能 | `LoopContext` Protocol 解耦、embedder LRU 复用、ProjectManager RLock、内存泄漏修复 4 处（_SEEN/orchestrator/embedding/enqueue）、`tool_schemas.py` 拆分、TaskOrchestrator 并发锁 |
| S5 功能补强 | Workflow DAG `/工作流 preview`、步骤失败实时 log、`/记忆状态`、委派摘要增强（决策高亮+文件统计）、`auto_title` 会话标题生成 |
| S6 测试/文档 | core 模块测试 4 个、gateway 模块测试 5 个、env 文档同步、覆盖率阈值 50→55 |

## 测试覆盖

**pytest**（默认排除 `live_llm`；CI 见 `.github/workflows/ci.yml`），覆盖：
- Transport 层（types、registry、chat_completions、anthropic、retry_utils）
- Provider 注册表（列表、查询、别名解析）
- Agent Loop 栈（`test_agent_loop.py`、`test_tool_batch.py`、`test_context_pipeline.py`）
- 工具系统（定义、dispatch、路径安全、envelope、审计）
- Tool guardrails（线程安全、warn JSON、halt/block）
- Orchestrator（系统提示、客户端创建、循环创建）
- Task Orchestrator（DAG、委派深度、execution_context / 审计 session）
- Gateway（`test_gateway_handler.py`、`test_gateway_session_registry.py`、hygiene）
- CC P0–P2 线束（`test_tool_result_storage.py`、`test_tool_prune_policy.py`、`test_read_state.py`、`test_loop_transition.py`、`test_message_queue.py`、`test_streaming_tools.py`、`test_cache_safe_delegate.py`、`test_gateway_queue_drain_push.py`）
- 外部对标（`test_runtime_metrics.py`、`test_gateway_queue_command.py`、`test_p2_workflow_permissions.py`）
- 体验增强（`test_p2_remaining_features.py`：总览、项目待办、管道、引导、自动续跑）
- 编排质量（`test_orchestration_improvements.py`：cron 提醒、向量检索、语义路由、MCP 自助、fact 提取、Skill 工具联动）
- OpenCode 对标（`test_opencode_features.py`）
- Sprint 改进（`test_delegate_context`、`test_loop_response`、`test_skill_tool_bridge`、`test_transcript_search`、`test_gateway_user_errors`、`test_gateway_help_commands`、`test_gateway_error_cards`、`test_command_registry`、`test_session_auto_title`）
- Report / CLI / Session lifecycle
- 真实 API smoke（可选）：`BUTLER_RUN_REAL_API_SMOKE=1 pytest -m live_llm tests/test_real_api_smoke.py`

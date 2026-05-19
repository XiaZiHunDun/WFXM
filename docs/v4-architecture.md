# Butler v4 架构文档

## 架构概述

Butler v4 采用**自建 Agent Loop + 模块化复用**方案 — Butler 完全控制自己的 Agent Loop，
不再 import Hermes AIAgent。仅从 Hermes 复用 Gateway 平台适配器（通过 subprocess），
Transport 层和 Provider Registry 均为 Butler 自建。

```
用户 ─→ CLI / 微信 / 其他平台
         │
         ▼
   Butler Orchestrator          ← 分层配置、记忆注入、Skill 路由
         │
         ▼
   Butler Agent Loop (自建)     ← 完全可控的 LLM 调用循环
         │
         ├─→ Transport Layer    ← 独立的 LLM 协议转换（chat_completions / anthropic）
         ├─→ Tool Registry      ← Butler 自建工具系统
         ├─→ Task Orchestrator  ← DAG 多 Agent 编排（真并行）
         └─→ Report Pipeline    ← 结构化报告 + 渐进披露
```

## 核心架构变更（v3 → v4）

| 维度 | v3 | v4 |
|------|----|----|
| Agent Loop | Hermes AIAgent (import) | Butler 自建 (~300 行) |
| LLM 调用 | 通过 AIAgent.run_conversation | 通过 LLMClient + Transport |
| 工具系统 | Hermes 50+ 工具 | Butler 自建 9 核心工具 |
| 子 Agent | Hermes delegate_task (绕过 Butler) | Butler 编排器全控 |
| 编排控制力 | 低（只能通过 prompt/hook 间接影响）| 完全（每一步可插手）|
| Hermes 升级风险 | 高（依赖内部 API）| 低（仅 Gateway subprocess）|
| 信息回传 | 未实现 | AgentReport 全链路 |

## 核心模块

### Butler Core (~1.2k 行)

| 模块 | 路径 | 说明 |
|------|------|------|
| Agent Loop | `butler/core/agent_loop.py` | 自建 LLM 循环：消息构造→LLM 调用→工具分发→上下文管理 |
| Orchestrator | `butler/orchestrator.py` | 系统提示注入、模型配置、Skill 路由、AgentLoop 工厂 |
| Task Orchestrator | `butler/task_orchestrator.py` | DAG 拓扑排序、真并行（asyncio.to_thread）、审批门控 |

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
| `terminal` | Shell 命令执行（可中断）|
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
| `butler/core/parallel_tools.py` | 安全并行工具批 |
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

完整对照见 [`docs/hermes-extraction-map.md`](hermes-extraction-map.md)。

### Agent Loop 数据流（含二次提炼）

```
用户消息 → sanitize_surrogates
    → 主循环:
        prepare: compress → repair → sanitize_api → drop_thinking_only
        LLM: interruptible complete/stream → sanitize_response
             → 空内容重试 / 截断续写 / failover（回合末恢复主模型）
        工具: normalize_tool_calls → parallel/sequential → steer 注入
    → LoopResult
```

### Gateway 层

| 模块 | 路径 | 说明 |
|------|------|------|
| 消息处理 | `butler/gateway/message_handler.py` | 平台消息→Butler Pipeline→格式化响应 |
| 平台适配 | 通过 Hermes subprocess | WeChat / Telegram / 20+ 平台 |

### 产品层（保留自 v3）

| 模块 | 路径 | 说明 |
|------|------|------|
| Agent 角色 | `butler/agent_profiles.py` | dev/content/review 三角色 |
| 分层记忆 | `butler/memory/` | ButlerMemory + ProjectMemory |
| Skill 系统 | `butler/skills/` | 加载/路由/自动合并 |
| 结构化报告 | `butler/report.py` | AgentReport + 渐进披露（/detail）|
| 后处理 | `butler/post_session.py` | 会话结束时记忆/技能提炼 |

## Agent Loop 设计

Butler v4 的 Agent Loop 是系统的核心——完全自建，不依赖任何外部 agent 框架：

```python
while not done and iterations < budget:
    1. 构造 messages（system + memory + skill + 对话历史）
    2. 调用 LLM（通过 Transport 层，支持流式）
    3. 解析响应：
       a. 纯文本 → 返回给编排器
       b. 工具调用 → 通过 Tool Registry 分发 → 结果追加到 messages
       c. 异常 → 按策略重试/降级
    4. 触发 callbacks（pre/post LLM、tool start/complete）
```

核心价值：**Butler 完全控制每一步**：
- 步骤 1 中可以自由注入/裁剪上下文
- 步骤 2 中可以灵活切换模型（甚至根据任务类型动态选择）
- 步骤 3b 中可以实现工具调用的 guardrails、权限控制
- 步骤 4 中可以实现任意粒度的 hooks

## 解决的设计痛点

| 痛点 | v3 状态 | v4 状态 |
|------|---------|---------|
| delegate_task 绕过 Butler | ❌ Hermes 控制 | ✅ Butler 全控 |
| 信息回传压缩 | ❌ 未实现 | ✅ AgentReport 链路 |
| 子 Agent 模型配置 | ❌ 不经过 Butler | ✅ AgentSpawnConfig |
| 子 Agent 工具集控制 | ❌ 缺失 | ✅ 可按角色过滤 |
| 会话隔离 | ❌ CLI 用进程内列表 | ✅ Gateway 按 session_key |
| Hermes 版本依赖风险 | ❌ 依赖内部 API | ✅ 仅 Gateway subprocess |
| 结构化报告 + /detail | ❌ 占位返回 | ✅ 完整实现 |

## 测试覆盖

505+ 项测试全部通过，覆盖：
- Transport 层（types、registry、chat_completions、anthropic）
- Provider 注册表（列表、查询、别名解析）
- Agent Loop（构造、消息管理、中断）
- 工具系统（定义、dispatch、读写文件、终端命令、目录列表）
- Orchestrator（系统提示、客户端创建、循环创建）
- Task Orchestrator（配置字段、拓扑排序、环检测、层分组）
- Report（新字段、缓存机制、CLI 格式化）
- Gateway Handler（命令处理、状态查看、模型查看）
- Agent Profiles（角色配置、模型感知提示）
- Main CLI（命令处理、无 Hermes import 验证）

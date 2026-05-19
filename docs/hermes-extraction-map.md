# Hermes-Agent → Butler v4 提炼对照表

> 版本: 2026-05-19 | 对应计划: Hermes 提炼优化

本文档记录从 `reference/hermes-agent` 提炼到 Butler v4 的模块映射、复制边界与验收状态。

## 设计原则

- **只移植算法与小模块**，不 import `AIAgent`、不复制 `run_agent.py` / `gateway/run.py` 单体。
- Butler 保留自建 `AgentLoop` + `Transport` + 产品层（记忆、Skill、DAG 编排）。
- Gateway 继续通过 Hermes **subprocess** 复用 20+ 平台。

## 模块对照表

| Butler 模块 | Hermes 参考 | 提炼内容 | 状态 |
|-------------|-------------|----------|------|
| `butler/core/agent_loop.py` | `run_agent.py`（片段） | guardrails 接线、并行工具、压缩入口、failover、interrupt | ✅ |
| `butler/tool_guardrails.py` | `agent/tool_guardrails.py` | before/after 护栏 | ✅（已移植，已接线） |
| `butler/core/message_repair.py` | `run_agent.py` `_repair_message_sequence` | role 交替、孤儿 tool、坏 JSON args | ✅ |
| `butler/transport/error_classifier.py` | `agent/error_classifier.py` | 429/401/overflow 分类 | ✅ |
| `butler/transport/fallback.py` | `run_agent.py` `_try_activate_fallback` | provider 链切换 | ✅ |
| `butler/transport/llm_client.py` | — | 接入 classifier + fallback | ✅ |
| `butler/core/context_compressor.py` | `agent/context_compressor.py` | 工具裁剪、头尾保护、LLM 摘要、parallel 对安全 | ✅ |
| `butler/transport/auxiliary_client.py` | `agent/auxiliary_client.py` | 压缩/post-session 便宜模型 | ✅ |
| `butler/core/parallel_tools.py` | `run_agent.py` 并行批 | 路径冲突检测、顺序保持 | ✅ |
| `butler/tools/interrupt.py` | `tools/interrupt.py` | 按 thread_id 中断 | ✅ |
| `butler/delegate_policy.py` | `tools/delegate_tool.py` | 深度上限、阻断工具 | ✅ |
| `butler/tools/registry.py` | `delegate_tool` + skills | 隔离子 loop、`skills_list`/`skill_view`、Report changes | ✅ |
| `butler/task_orchestrator.py` | DAG + delegate 信封 | 子 agent 空历史、阻断 delegate、changes 提取 | ✅ |
| `butler/session_lifecycle.py` | `memory_manager` 生命周期 | `trigger_session_end`、`sync_turn` 跳过 interrupt | ✅ |
| `butler/gateway/hooks.py` | `hermes_cli/plugins.py`（子集） | `pre_gateway_dispatch` 等轻量 HookBus | ✅ |
| `butler/skills/guard.py` | `tools/skills_guard.py` | 社区 skill 静态扫描 | ✅ |

## 明确不移植

| Hermes 路径 | 原因 |
|-------------|------|
| `run_agent.py` (~790KB) | 违背 v4 自建 Loop；维护成本极高 |
| `gateway/run.py` (~16k 行) | Butler 已 subprocess 使用 |
| 50+ 工具 / MCP / 浏览器 / 沙箱 | 超出 Butler「9 核心工具 + 项目开发」定位 |
| `hermes_state.SessionDB` | 与 Butler 项目记忆模型重复 |
| 完整 Plugin 平台 / skills hub | 强依赖 Hermes 全局状态 |
| Codex/Bedrock/Gemini 全协议栈 | 按需再加；当前 2 协议已覆盖国内主力 |

## Sprint 验收

| Sprint | 目标 | 测试 |
|--------|------|------|
| 1 Loop 生产化 | guardrails、error_classifier、message_repair、fallback | `tests/test_hermes_extraction.py`, `test_agent_loop.py`, `test_llm_client.py` |
| 2 上下文与辅助模型 | `context_compressor` + `auxiliary_client` | 压缩 fixture、`test_butler_v4.py` |
| 3 工具与委派 | 并行批、interrupt、delegate 信封 | `test_hermes_extraction.py`, `test_tools_registry.py` |
| 4 记忆/Gateway/Skills | session 边界、HookBus、skills_guard | `test_gateway_handler.py`, `test_main_cli.py` |

全量测试目标：**492+ passed**（`pytest tests/`）。

## 架构约束

- `butler/core/agent_loop.py` 保持 **< 600 行**（当前 ~417 行）。
- 业务逻辑不得回灌到单体 `run_agent.py` 风格文件。
- 新增 Hermes 能力优先新建 `butler/core/*` 或 `butler/transport/*` 模块。

## 后续可选

- Gateway 空闲 85% 阈值卫生压缩（Hermes `gateway/run.py` 模式）
- `MemoryManager` 完整 prefetch/sync 接口与 Honcho 插件对齐
- metadata-only Skill 索引与 `SkillRouter` 动态切换策略

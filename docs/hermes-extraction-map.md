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

全量测试目标：**505+ passed**（`pytest tests/`）。

## 架构约束

- `butler/core/agent_loop.py` 保持 **< 600 行**（当前 ~487 行，编排为主）。
- 业务逻辑不得回灌到单体 `run_agent.py` 风格文件。
- 新增 Hermes 能力优先新建 `butler/core/*` 或 `butler/transport/*` 模块。

## run_agent.py 二次提炼（AIAgent L1028–L15213）

| Butler 模块 | Hermes 行号 | 能力 | 状态 |
|-------------|-------------|------|------|
| `butler/transport/content_sanitize.py` | L3539–L3615 | think/XML 泄漏清理、流式 delta 过滤 | ✅ |
| `butler/core/message_sanitize.py` | L5837–L5905 | 角色白名单、stub tool result、thinking-only 丢弃 | ✅ |
| `butler/core/tool_call_normalize.py` | L6047–L6115 | 去重、工具名修复、delegate 并发上限 | ✅ |
| `butler/core/loop_response.py` | L3516, empty retry | 空响应/截断续写判定 | ✅ |
| `butler/transport/interruptible_client.py` | L7166–L7484 | 可中断 API + stale 超时 | ✅ |
| `butler/core/steer.py` | L5180–L5293 | `/steer` 不打断插话 | ✅ |
| `butler/core/delegate_context.py` | L10225 回调传播 | 子 loop 工具进度回调 | ✅ |
| `butler/core/iteration_budget.py` | L283–L325 | 迭代预算（可选） | ✅ |
| `butler/core/agent_loop.py` + `butler/core/loop_types.py` | 回合边界 | failover 回合恢复、空内容重试、截断续写、Loop 公共类型 | ✅ |

测试：`tests/test_run_agent_extraction.py`；全量 **505+ passed**。

## CLI 提炼层（2026-05 增补）

| Butler 模块 | 参考 | 能力 |
|-------------|------|------|
| `butler/cli/display.py` | `agent/display.py` | 工具预览、完成行、失败检测、write/patch 内联 diff |
| `butler/cli/stream.py` | `cli.py` + v1 `_StreamBox` | 行缓冲流式输出、边框、流结束 Markdown 重渲染 |
| `butler/cli/spinner.py` | `KawaiiSpinner`（简化） | LLM 等待指示 |
| `butler/cli/session_ui.py` | `HermesCLI` 回调 | 统一 `LoopCallbacks` 接线 |
| `butler/main.py` | v1 `cli_adapter.py` | `patch_stdout`、历史自动建议 |

## Sprint E：国产模型加固

| Butler 模块 | Hermes 参考 | 能力 | 状态 |
|-------------|-------------|------|------|
| `butler/transport/reasoning_replay.py` | `run_agent.py` L9734+ | DeepSeek/Kimi `reasoning_content` 出站回放与占位 | ✅ |
| `butler/core/json_repair.py` | L666–L802 | 工具参数 JSON 深度修复（尾逗号、未闭合、控制符） | ✅ |
| `butler/transport/think_scrubber.py` | `agent/think_scrubber.py` | 流式 think 状态机（跨 chunk 边界） | ✅ |
| `butler/transport/chat_completions.py` | `_copy_reasoning_content_for_api` | `convert_messages` / `build_kwargs` 注入回放 | ✅ |
| `butler/transport/llm_client.py` | `_fire_stream_delta` | 流式 `StreamingThinkScrubber` + provider 上下文 | ✅ |
| `butler/core/agent_loop.py` | `_build_assistant_message` | 会话内持久化 `reasoning` / `reasoning_content` | ✅ |
| `butler/transport/schema_sanitizer.py` | `tools/schema_sanitizer.py` | strict / 本地后端工具 schema 清洗、`pattern`/`format` 失败后降级 | ✅ |
| `butler/transport/retry_utils.py` | `agent/retry_utils.py` | transient API 失败的指数退避 + jitter + 上限 | ✅ |
| `butler/gateway/message_handler.py` + `butler/transport/model_context.py` | `gateway/run.py` L7113+ | Gateway 常驻会话 85% 卫生压缩、模型上下文推断 | ✅ |
| `butler/session_lifecycle.py` | `memory_provider` / post-session hooks | turn 前记忆预取、turn 后同步、session end 抽取 | ✅ |
| `butler/skills/manager.py` + `butler/skills/router.py` + `butler/orchestrator.py` | Skill metadata 路由模式 | frontmatter-only Skill 索引、mtime cache、命中后动态加载正文 | ✅ |
| `butler/core/agent_loop.py` + `butler/gateway/message_handler.py` | Gateway/Loop health summary | runtime diagnostics 聚合与 `/health`/`/诊断` 命令（压缩、schema 降级、Skill、记忆同步） | ✅ |
| `butler/core/hygiene_preflight.py` + `butler/core/schema_recovery.py` + `butler/core/retry_policy.py` | AgentLoop 策略拆分 | hygiene 预检、schema 恢复、retry delay 策略模块化 | ✅ |
| `butler/execution_context.py` + `butler/tools/registry.py` + `butler/task_orchestrator.py` | 委派执行上下文 | Gateway/CLI/tool 子路径复用宿主 orchestrator，子代理对齐 Skill 注入与 turn memory lifecycle | ✅ |
| `butler/tools/path_safety.py` + `butler/tools/registry.py` | 工具路径安全 | 项目 workspace sandbox、敏感路径 denylist、文件/搜索/terminal 路径与 workdir 统一校验 | ✅ |
| `butler/gateway/session_registry.py` + `butler/gateway/message_handler.py` | Gateway session registry | 按 `session_key` 管理 AgentLoop、health、idle TTL/LRU 驱逐和 session finalize | ✅ |
| `butler/task_orchestrator.py` | TaskOrchestrator 调度/深度 | 子代理工具 dispatcher 继承委派深度，parallel/graph 异常转结构化结果，router 分支与依赖失败 fail-closed | ✅ |
| `butler/tools/registry.py` | 工具安全收尾 | `read_file` 大小/行数上限、`search_files` 结果路径二次校验、terminal timeout/output 上限 | ✅ |
| `butler/tools/registry.py` | 工具原子写入 | `write_file`/`patch` 拒绝 symlink、hardlink、非普通文件目标，并通过同目录临时文件原子替换 | ✅ |
| `butler/tools/registry.py` + `butler/gateway/message_handler.py` | 工具输出与审计观测 | 工具错误兼容式 envelope、错误码分类、脱敏审计事件和 `/health` 工具摘要 | ✅ |

测试：`tests/test_cn_model_hardening.py`、`tests/test_schema_sanitizer.py`、`tests/test_retry_utils.py`、`tests/test_model_context.py`、`tests/test_session_lifecycle.py`、`tests/test_butler_skills.py`、`tests/test_orchestrator.py`。真实 API smoke tests 位于 `tests/test_real_api_smoke.py`，默认被 `live_llm` marker 排除；显式运行需使用 `pytest -m live_llm tests/test_real_api_smoke.py`，并设置 `BUTLER_RUN_REAL_API_SMOKE=1` 和对应 provider API key。

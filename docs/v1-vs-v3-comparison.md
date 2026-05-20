# Butler v1 vs v3 对比

> **当前实现为 Butler v4**（自建 Loop，不 import Hermes AIAgent）。v4 与 v3 差异见 [`v4-architecture.md`](v4-architecture.md)「核心架构变更（v3 → v4）」表。

## 架构对比

| 维度 | Butler v1 | Butler v3 |
|------|-----------|-----------|
| **基础引擎** | 自研 AgentRunner (~600 行) | Hermes AIAgent (15k 行成熟引擎) |
| **集成方式** | 从零构建的单体系统 | 直接 `import AIAgent`，嵌入式集成 |
| **代码量** | ~14.5k 行 (含 ~7k 死代码) | ~2.5k 行 Butler 层 + ~300k 行 Hermes 底座 |
| **可维护性** | 需自行维护全部引擎代码 | Butler 层独立，Hermes 底座跟随上游 |

## 功能对比

### LLM 支持

| 能力 | v1 | v3 |
|------|----|----|
| Provider 数量 | 5 (MiniMax/OpenAI/Claude/DeepSeek/Qwen) | 30+ (含所有 v1 + Gemini/Mistral/Bedrock/Groq/Kimi 等) |
| 协议支持 | OpenAI 兼容 (chat completions) | 4 种: chat_completions / anthropic_messages / codex_responses / bedrock_converse |
| 模型切换 | `/model` 命令 | `/model` + 按角色配置 + provider fallback chain |
| 流式输出 | 主 Agent 可用，子 Agent 不可用 | 主 Agent + 子 Agent 均可用 |

### 通讯平台

| 平台 | v1 | v3 |
|------|----|----|
| CLI | ✅ 自研 (prompt_toolkit + Rich) | ✅ Rich CLI + Hermes AIAgent 直接驱动 |
| 微信 | ✅ iLink Bot API | ✅ Hermes weixin adapter + Butler Plugin Hook |
| Telegram | ❌ | ✅ |
| Discord | ❌ | ✅ |
| Slack | ❌ | ✅ |
| 飞书 | ❌ | ✅ |
| 钉钉 | ❌ | ✅ |
| Signal / Matrix / 邮件 / 短信 等 | ❌ | ✅ |
| **总计** | **2 平台** | **20+ 平台** |

### 工具系统

| 维度 | v1 | v3 |
|------|----|----|
| 内置工具数 | 27 | 50+ |
| 浏览器自动化 | ❌ | ✅ (Playwright) |
| MCP 支持 | 基础 | ✅ 完整 |
| 代码执行沙箱 | ❌ | ✅ (Modal/Daytona/Vercel) |
| 子代理委派 | 自研 (有 Bug) | ✅ Hermes delegate_task + Butler DAG 编排 |
| 语音 (TTS/STT) | ❌ | ✅ (Edge TTS + Whisper) |
| Kanban 看板 | ❌ | ✅ |
| Dashboard | ❌ | ✅ (Web SPA) |

### Butler 产品特有功能

| 功能 | v1 | v3 |
|------|----|----|
| 管家-项目层次 | ✅ | ✅ |
| 分层记忆 (Butler 层) | ✅ ProfileStore + ExperienceStore | ✅ 同架构 + MemoryProvider 插件注册 |
| 分层记忆 (项目层) | ✅ MarkdownMemory + ProjectFacts | ✅ 同架构 |
| 后台记忆提取 | ⚠️ 代码有但 llm_call=None 从未运行 | ✅ sync_turn 触发后台双通道提取 |
| Skill 自动合并 | ✅ 三层漏斗 + LLM 合并 | ✅ 同架构 |
| Skill 路由注入 | ✅ | ✅ 每条消息注入 |
| 多角色模型配置 | ✅ LayeredModelConfig | ✅ 三级合并 (全局 → 项目 → 运行时) |
| 报告格式化 | ✅ CLI / WeChat | ✅ CLI / WeChat |
| 项目管理 | ✅ | ✅ |
| DAG 编排 | ⚠️ 代码有但未接入运行时 | ✅ 真并行 (`asyncio.to_thread`) |
| Agent Profiles | ✅ 3 角色 | ✅ 3 角色 + ephemeral_system_prompt 注入 |
| Tool Guardrails | ✅ | ✅ |

### Agent 引擎能力

| 能力 | v1 | v3 |
|------|----|----|
| Agent Loop 健壮性 | 基础 (单次请求循环) | 高级 (多轮、错误恢复、fallback、重试) |
| 并行工具执行 | ❌ (guardrails 默认禁用) | ✅ |
| Context 压缩 | ❌ | ✅ (自动摘要 + token 管理) |
| Session 持久化 | SQLite 基础实现 | Hermes 完整 session 管理 |
| 子代理系统 | 基础委派 (流式不可用) | 完整的 delegate_task + context 隔离 |
| Plugin 架构 | ❌ | ✅ (标准化 plugins/ 目录) |
| Cron 定时任务 | ❌ | ✅ |

## 已知缺陷对比

### v1 遗留问题 (未修复)

1. AgentRunner 流式检测 `complete_stream()` 而 Provider 只实现 `stream()` — 子 Agent 永远不流式
2. 并行工具在 guardrails=True (默认) 时被禁用 — 实际永远串行
3. PostSessionProcessor 的 `llm_call` 默认为 None — 记忆/技能自动提取从未运行
4. ~7k 行死代码 (context_compressor、token_budget、verify_loop、task_orchestrator)

### v3 已修复的 Bug

1. ~~`final_response` 键错误~~ → 已改为正确键名，Rich Markdown 渲染正常
2. ~~Gateway Plugin 用 dict 操作 dataclass~~ → 已适配 `MessageEvent` dataclass + action dict 协议
3. ~~asyncio.gather 中同步阻塞~~ → 已用 `asyncio.to_thread` 包装实现真并行
4. ~~后台记忆提取使用错误键~~ → 已修复，提取可正常工作
5. ~~Butler 插件不自动加载~~ → `butler gateway` 启动时自动 enable

## 测试覆盖

| 指标 | v1 | v3 |
|------|----|----|
| 测试文件 | 4 | 1 (集中) + Hermes 原有测试 |
| 测试用例 | 102 | 44 (Butler 层 — 全部通过) |
| 测试类型 | 单元 + 集成 + E2E LLM | 单元 + 集成 |

## 结论

**v3 是最终版本**。原因：

1. **v1 的全部产品功能已完整移植**，且修复了 v1 的多个遗留 Bug（后台提取不工作、DAG 未接入、并行被禁用）
2. **Hermes 引擎带来质的飞跃**: 30+ Provider、20+ Gateway、50+ 工具、浏览器自动化、MCP、沙箱
3. **零 Fork 架构**: 不改 Hermes 代码，可跟随上游更新
4. **Butler 层轻量独立**: ~2.5k 行专注于产品差异化，易维护

v1 归档于 `archive/butler-v1/`，供参考和回溯。

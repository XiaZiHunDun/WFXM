# Butler v1 vs v2 对比文档

## 架构对比

| 维度 | Butler v1 | Butler v2 |
|------|-----------|-----------|
| **基础引擎** | 自研 AgentRunner (~600行) | Hermes AIAgent (15k行成熟引擎) |
| **代码量** | ~14.5k行 Python | ~3.3k行 Butler层 + ~302k行 Hermes底座 |
| **架构模式** | 从零构建的单体系统 | Fork hermes + Butler产品层叠加 |
| **Python 文件数** | 73 | 18(Butler) + 384(Hermes) = 402 |

## 功能对比

### LLM 支持

| 能力 | v1 | v2 |
|------|----|----|
| Provider 数量 | 5 (MiniMax/OpenAI/Claude/DeepSeek/Qwen) | 30+ (含所有 v1 + Gemini/Mistral/Bedrock/Groq/Kimi/零一万物等) |
| 协议支持 | OpenAI兼容 (chat completions) | 4种: chat_completions / anthropic_messages / codex_responses / bedrock_converse |
| 模型切换 | `/model` 命令 | `/model` + provider profile + 动态 fallback 链 |
| 流式输出 | 基础实现 | 并行工具执行 + 流式 + 错误恢复 |

### 通讯平台

| 平台 | v1 | v2 |
|------|----|----|
| CLI | ✅ 自研 (prompt_toolkit + Rich) | ✅ Hermes CLI (成熟的 TUI) |
| 微信 (WeChat) | ✅ iLink Bot API | ✅ Hermes weixin adapter |
| Telegram | ❌ | ✅ |
| Discord | ❌ | ✅ |
| Slack | ❌ | ✅ |
| 飞书 (Feishu) | ❌ | ✅ |
| 钉钉 (DingTalk) | ❌ | ✅ |
| Signal | ❌ | ✅ |
| Matrix | ❌ | ✅ |
| 邮件 (Email) | ❌ | ✅ |
| 短信 (SMS) | ❌ | ✅ |
| Home Assistant | ❌ | ✅ |
| **总计** | **2 平台** | **20+ 平台** |

### 工具系统

| 维度 | v1 | v2 |
|------|----|----|
| 内置工具数 | 27 | 50+ |
| 浏览器自动化 | ❌ | ✅ (Playwright) |
| MCP 支持 | 基础 | ✅ 完整 |
| 代码执行沙箱 | ❌ | ✅ (Modal/Daytona/Vercel) |
| 子代理委派 | 自研 task_orchestrator | ✅ Hermes delegate_task |
| Kanban 看板 | ❌ | ✅ |
| 语音 (TTS/STT) | ❌ | ✅ (Edge TTS + Whisper) |
| 计算机操控 | ❌ | ✅ (cua-driver MCP) |

### Butler 产品特有功能

| 功能 | v1 | v2 |
|------|----|----|
| 管家-项目层次 | ✅ 自研 | ✅ 重新实现 |
| 分层记忆 (Butler层) | ✅ ProfileStore + ExperienceStore | ✅ 同架构重新实现 |
| 分层记忆 (项目层) | ✅ MarkdownMemory + ProjectFacts | ✅ 同架构重新实现 |
| Hermes MemoryProvider 集成 | ❌ | ✅ ButlerMemoryProvider 插件 |
| Skill 自动合并 | ✅ 三层漏斗 + LLM合并 | ✅ 同架构重新实现 |
| Skill 路由注入 | ✅ SkillRouter | ✅ 同架构重新实现 |
| 多角色模型配置 | ✅ LayeredModelConfig | ✅ 三级合并 (全局→项目→运行时) |
| 报告格式化 | ✅ CLI/WeChat/Detail | ✅ 四路格式化 (CLI/WeChat/Butler-LLM/Detail) |
| 项目管理 | ✅ ProjectManager | ✅ 同架构重新实现 |

### Agent 引擎能力

| 能力 | v1 | v2 |
|------|----|----|
| Agent Loop 健壮性 | 基础 (单次请求循环) | 高级 (多轮、错误恢复、fallback、重试) |
| 并行工具执行 | ❌ | ✅ |
| Context 压缩 | ❌ | ✅ (自动摘要 + token 管理) |
| Session 持久化 | SQLite 基础实现 | Hermes 完整 session 管理 |
| 子代理系统 | 基础委派 | 完整的 delegate_task + context 隔离 |
| Plugin 架构 | ❌ | ✅ (标准化的 plugins/ 目录) |
| Cron 定时任务 | ❌ | ✅ |
| Dashboard | ❌ | ✅ (Web SPA) |

## 测试覆盖

| 指标 | v1 | v2 |
|------|----|----|
| 测试文件 | 4 | 4 (Butler层) + Hermes 原有测试 |
| 测试用例 | 102 | 58 (Butler层 — 全部通过) |
| 测试类型 | 单元 + 集成 + E2E LLM | 单元 + 集成 |
| 覆盖范围 | 所有 Butler 模块 | 所有 Butler v2 模块 |

## 性能与可维护性

| 维度 | v1 | v2 |
|------|----|----|
| 启动速度 | 快 (轻量) | 较慢 (Hermes 加载大量模块) |
| 依赖复杂度 | 低 (~15 核心依赖) | 高 (~30 核心依赖 + 大量可选) |
| 代码可维护性 | 简单，但需要自行维护引擎 | Butler 层简洁，Hermes 底座由社区维护 |
| 扩展性 | 需要手写所有新能力 | 可直接使用 Hermes 生态插件 |
| 安全沙箱 | ❌ | ✅ (Modal/Daytona 远程沙箱) |

## 结论

**v2 的核心优势：**
1. 继承 Hermes 的 20+ 通讯平台适配器，免去大量对接工作
2. 30+ LLM Provider + 4种协议，模型兼容性大幅提升
3. 成熟的 Agent Loop (15k行)，健壮性远超 v1 的 600 行自研引擎
4. 50+ 内置工具，含浏览器自动化、MCP、沙箱执行等高级能力
5. Butler 产品层独立性好，所有 v1 特有功能均已移植

**v2 的风险：**
1. Hermes 代码量大 (~302k行)，单文件 15k 行增加调试难度
2. 依赖链更长，部分 Hermes 依赖需要付费 API key
3. Hermes 更新时需要手动合并上游变更

**推荐：采用 v2**，因为 Butler 层的核心差异化功能 (3.3k行) 已完整移植，而 Hermes 带来的工程成熟度和平台生态是从零构建难以企及的。

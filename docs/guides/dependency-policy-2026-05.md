# 依赖分层与引入策略（2026-05）

> **更新**：2026-05-26  
> **用途**：说明 Butler 当前已经引入哪些依赖、哪些依赖是可选安装、哪些依赖明确不引入。  
> **事实源**：依赖包名以 [`../../pyproject.toml`](../../pyproject.toml) 为准；产品边界以 [`../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md`](../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md) 为准。

## 1. 原则

Butler v4 的依赖策略只有三条：

1. `core` 默认最小化，只保留 Loop、Transport、配置和本地状态主路径必需依赖。
2. 微信、MCP、OCR、voice、PTY、开发工具等能力优先进入 `optional-dependencies`。
3. 文件 / JSONL 仍是事实源；SQLite 是派生索引层，不因为引入 `aiosqlite` 就把 Butler 改成 SQL 平台。

对应架构说明见 [`../architecture/v4-architecture.md`](../architecture/v4-architecture.md) §依赖分层与本地状态原则。

## 2. 已引入的 core 依赖

以下依赖来自 `pip install -e .`，即 `pyproject.toml` `[project.dependencies]`：

| 分组 | 依赖 | 说明 |
|------|------|------|
| LLM / Transport | `openai`、`anthropic`、`httpx[socks]`、`requests` | 模型调用与 HTTP 访问 |
| 配置 / 模板 / 校验 | `python-dotenv`、`pyyaml`、`jinja2`、`pydantic` | 环境、配置、模板与数据结构 |
| CLI / 交互 | `rich`、`prompt_toolkit` | 命令行输出与交互 |
| 重试 / 调度 / 运行环境 | `tenacity`、`croniter`、`psutil`、`tzdata` | 重试、定时、进程信息与平台兼容 |
| 安全 / 认证 | `PyJWT[crypto]` | JWT 与加密支持 |
| 中文 / 本地状态 | `jieba`、`aiosqlite` | 中文分词与 SQLite 派生索引 |

说明：

- 当前 `core` 共 **17** 项依赖，其中 `tzdata` 仅在 Windows 下启用。
- `aiosqlite` 的引入目的是本地派生查询层，例如 `observations.db`，不是替代 `transcript.jsonl`。

## 3. 已引入的 optional extras

以下依赖按场景安装，不进入默认 `core`：

| extra | 安装命令 | 依赖 | 用途 |
|------|----------|------|------|
| `wechat` | `pip install -e ".[wechat]"` | `aiohttp`、`certifi`、`qrcode`、`cryptography` | 微信 iLink 网关 |
| `mcp` | `pip install -e ".[mcp]"` | `mcp` | 薄 MCP client |
| `voice` | `pip install -e ".[voice]"` | `faster-whisper`、`sounddevice`、`numpy` | 语音 / STT / TTS |
| `wechat-ocr` | `pip install -e ".[wechat-ocr]"` | `pytesseract`、`pillow` | OCR / 图片辅助 |
| `cli` | `pip install -e ".[cli]"` | `simple-term-menu` | CLI 菜单增强 |
| `pty` | `pip install -e ".[pty]"` | `ptyprocess` 或 `pywinpty` | PTY 兼容层 |
| `dev` | `pip install -e ".[dev]"` | `debugpy`、`pytest`、`pytest-asyncio`、`ruff` | 开发 / 测试 / Lint |
| `all` | `pip install -e ".[all]"` | 聚合 `wechat`、`wechat-ocr`、`cli`、`dev`、`voice`、`pty` | 便捷安装集合 |

补充说明：

- `all` **不包含** `mcp`，需要时仍应单独安装 `.[mcp]`。
- `cryptography` 虽已在 `wechat` extra 中存在，但“凭证 Fernet 加密”仍属于产品层待选能力，不等于该能力已经默认启用。
- `mcp` 只是可选薄客户端，功能开关仍受 `BUTLER_MCP_ENABLED` 控制。

## 4. 明确不引入的依赖

下列依赖或技术栈目前**明确不作为 Butler 运行时依赖引入**：

| 类别 | 代表项 | 依据 | Butler 当前替代 |
|------|--------|------|-----------------|
| 重基础设施 | Redis、Postgres、Kafka、RabbitMQ、NATS | [`roadmap-backlog`](../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md) §2.4 | `transcript.jsonl`、文件状态、SQLite 派生索引、durable outbox |
| 平台型 Agent 框架 | LangChain、LangGraph、Hermes `AIAgent` | [`external-reference-deferred`](./external-reference-deferred-2026-05.md) §3 | Butler 自建 `agent_loop` + `task_orchestrator` |
| 浏览器 / Studio 平台 | browser-use CDP、Playwright 农场、RAGFlow Studio、Langflow 画布 | [`four-reports-out-of-scope`](../plans/decisions/four-reports-out-of-scope-2026-05.md) | `web_fetch`、`terminal`、CLI / 微信 |
| 全量 MCP Host / 桌面壳 | Electron、Tauri、全量 MCP Host | [`../architecture/v4-architecture.md`](../architecture/v4-architecture.md) §依赖分层与本地状态原则 | 微信 Gateway + 薄 MCP client |
| 外部 APM / Tracing 默认接入 | LangSmith、OTEL 全量默认接入、`prometheus-client` | [`four-reports-out-of-scope`](../plans/decisions/four-reports-out-of-scope-2026-05.md) · [`../plans/archive/reference-learning-plan-2026-05.md`](../plans/archive/reference-learning-plan-2026-05.md) | `runtime_metrics` + `/诊断` |
| 参考仓运行时栈 | `reference/` 内任意产品依赖 | [`../DOCUMENTATION.md`](../DOCUMENTATION.md) §6.4 | 学模式，不搬技术栈 |

## 5. 仍可单独立项，但默认不进 core

这些方向不是当前默认依赖，但若后续立项，仍应优先评估走 optional extra：

| 项 | 当前状态 | 备注 |
|----|----------|------|
| 凭证 Fernet 加密 | 可选 Backlog | 依赖 `cryptography`，但能力尚未作为默认路径落地 |
| OpenAPI 声明式 HTTP 工具 | 可选 Backlog | 需要产品定义 `.butler/tools/*.yaml` 方案 |
| 全量 RAG ingest 管线 | 可选 Backlog | 不是当前轻量检索主路径 |
| execute_code 生产开放 | 可选 Backlog（需安全评审） | 即使落地也不应默认开启 |

详见 [`../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md`](../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md) §3。

## 6. 维护规则

改 `pyproject.toml` 中的 `dependencies` 或 `optional-dependencies` 时，需同步检查：

1. [`../config/reference.md`](../config/reference.md) 的安装与依赖分层表
2. 本文是否需要更新 `core` / `extra` / `不引入` 分类
3. [`../architecture/v4-architecture.md`](../architecture/v4-architecture.md) 的依赖分层原则是否仍成立
4. 若触及产品边界，是否要同步 [`../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md`](../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md)

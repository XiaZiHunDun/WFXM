# Butler · 微信 AI 管家

> **English**: A self-hosted **personal AI butler** for **multiple projects** — talk on **WeChat** or the **CLI**, delegate coding and writing to role agents, with layered memory and optional MCP extensions.

**Butler v4** 是自建的 Agent 平台：核心循环在 `butler/core/`，微信网关为 Butler 原生实现（**不**依赖 Hermes `AIAgent` 或 IDE 子进程）。  
适合「远程用手机指挥多个仓库/小说/软件项目」的个人或小团队场景。

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## 是什么

Butler 是 **多项目 AI 管家**：

- 你在 **微信** 或终端里用自然语言 / 斜杠命令下指令  
- Butler（Lead）理解意图后，**委派**给开发 / 内容 / 审核等子代理改代码、写文档、跑验证  
- **分层记忆**（Owner 画像、项目 MEMORY、向量检索、ingest 写盘）跨会话延续上下文  
- 每个项目在独立 **workspace** 下运行，带权限门控与人工确认

**典型主路径**：`/切换 项目` → `/简报` 看状态 → 「交给开发代理…」或 `/改` 结构化委派 → 验收卡确认结果。

---

## 核心能力

| 能力 | 说明 |
|------|------|
| **微信网关** | `butler gateway` + iLink；入站队列、`/steer`、出站重试与 durable outbox |
| **自建 Agent Loop** | 上下文压缩、工具结果落盘、read-before-edit、委派 cache-safe 前缀 |
| **多项目** | `project.yaml`、Lead 模式、项目切换、runtime 定时任务 |
| **委派与验收** | `delegate_task`、Dev 自动 verify 门控、Owner **验收卡**（ingest 等只读写盘单独语义） |
| **记忆** | 语义检索、fact 提取、记忆待审、`butler memory ingest`、EXT-5 MarkItDown → `.butler/ingest/` |
| **扩展（opt-in）** | 薄 MCP 客户端（GitHub / Todoist / Firecrawl / MarkItDown 等）；见 Extension R&D 规程 |
| **可观测** | `/诊断`、`butler doctor`、runtime 指标；LangFuse 可选 |

---

## 不是什么

为避免误解，下列能力 **不在产品边界内**（详见 [roadmap §1 否决](docs/plans/decisions/roadmap-backlog-and-boundaries-2026-05.md)）：

- 全量 MCP Host / IDE 内置 Agent / 多租户 SaaS  
- 用 LangGraph 等 **替换** 自建 Loop  
- 微信内代码 diff 阅读器、无限制 shell、浏览器自动化默认路径  

我们对标的是 **「微信 + 多项目管家」**，Dev 能力上限参考 Claude Code **CLI** 线束，而非 Cursor IDE 全家桶。

---

## 架构一览

```
Owner ──→ 微信 / CLI / Gateway
              │
              ▼
        Butler Orchestrator     记忆 · Skill · 分层模型
              │
              ▼
        Agent Loop (core/)      context · retry · tool_batch · delegate
              │
              ├─ Transport      多 Provider（OpenAI 兼容 / Anthropic）
              ├─ Tools          内置 + 可选 MCP + 项目白名单
              └─ Gateway        message_handler · 队列 · 出站
```

实现细节：[v4-architecture.md](docs/architecture/v4-architecture.md) · 解耦说明：[hermes-decoupling.md](docs/architecture/hermes-decoupling.md)

---

## 快速开始

### 1. 安装

```bash
git clone https://github.com/XiaZiHunDun/WFXM.git
cd WFXM
pip install -e ".[wechat]"    # Butler + 微信网关依赖
```

### 2. 配置

先读 **[部署三剖面](docs/guides/deploy-profiles-2026-06.md)**（gateway / dev-local / dev-remote），再编辑环境变量：

```bash
cp .env.example .env
# 至少配置一个 LLM API Key（如 MINIMAX_API_KEY、DEEPSEEK_API_KEY）
```

变量全集：[config/reference.md](docs/config/reference.md) · 示例：[`.env.example`](.env.example)

### 3. 运行

```bash
# 新机 / 新 Owner 上手（一页纸清单）
butler onboard --profile gateway

# 终端对话
butler chat

# 单条指令
butler exec "列出所有项目"

# 微信网关（生产主场景）
butler wechat-setup
bash scripts/install-butler-gateway-service.sh
bash scripts/butler-gateway-ops.sh status
```

### 4. 验证

发版以 **分层 gate** 为准（非裸跑全量 `pytest tests/`）：

```bash
bash scripts/butler-pytest-fast-gate.sh
bash scripts/project-health-check.sh quick
```

策略说明：[agent-testing-strategy](docs/plans/decisions/agent-testing-strategy-2026-06.md)

---

## 微信 Owner 常用命令

| 说法 / 命令 | 作用 |
|-------------|------|
| `/切换 项目名` | 切换当前工作项目 |
| `/简报` | 待办 · 队列 · 门控 · 昨夜 job |
| `/帮助` | 五意图首屏（查 · 改 · 批 · 记 · 管） |
| `/改 …` | 结构化开发/内容委派 |
| `/诊断` | 运行时健康与 MCP Extension 状态 |
| `/反馈 …` | Owner 硬反馈（观测闭环） |

扩展验收话术：[EXT-5 微信话术卡](docs/guides/ext5-wechat-phrases-card-2026-06.md)

---

## 仓库结构

```
butler/
├── core/           Agent Loop、上下文、委派门控
├── gateway/        微信入站/出站、message_handler
├── transport/      LLM Provider 与协议
├── tools/          工具注册表、MCP、delegate
├── memory/         向量、ingest、observation store
├── dev_engine/     开发验证与编码知识层
└── main.py         CLI 入口
docs/               架构、配置、规划（索引 docs/README.md）
scripts/            网关运维与守门脚本
tests/              自动化测试（分层 gate）
```

更完整目录说明：[STRUCTURE.md](STRUCTURE.md)

---

## 文档导航

| 读者 | 从这里开始 |
|------|------------|
| **新用户 / 运维** | [deploy-profiles](docs/guides/deploy-profiles-2026-06.md) → [wechat-gateway-ops](docs/guides/wechat-gateway-ops.md) |
| **开发者** | [AGENTS.md](AGENTS.md) → [v4-architecture](docs/architecture/v4-architecture.md) |
| **提需求 / 边界** | [roadmap-backlog](docs/plans/decisions/roadmap-backlog-and-boundaries-2026-05.md) |
| **发版** | [release-runbook](docs/guides/release-runbook-2026-05.md) |
| **文档体系** | [DOCUMENTATION.md](docs/DOCUMENTATION.md) |

---

## 参与开发

- 改 `butler/core` 或 `butler/gateway` 前请读 [AGENTS.md](AGENTS.md) 守门清单  
- 贡献约定：[CONTRIBUTING.md](CONTRIBUTING.md)  
- Cursor 规则：`.cursor/rules/`

---

## License

MIT — 见 [LICENSE](LICENSE)。

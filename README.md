> 当前状态：Butler v5 是唯一活动产品主线；Butler v4 已退役并只读归档（ADR-0001）。

[![CI](https://github.com/XiaZiHunDun/WFXM/actions/workflows/ci.yml/badge.svg)](https://github.com/XiaZiHunDun/WFXM/actions/workflows/ci.yml)

# Butler v5 · 可扩展个人 AI 管家

> **English**: A self-hosted, single-owner personal AI butler with WeChat, CLI/API, tool execution, delegation, durable events, and governed extension points.

**Butler v5** 是单 Owner、单信任域、本机自托管的个人 AI 管家。当前主入口是微信，CLI/API/WebSocket 提供运维、集成和异步结果通道。认知环、权限与数据均由本项目掌控，不依赖 Hermes `AIAgent` 或浏览器端 Agent Runtime。

[![Node.js 20](https://img.shields.io/badge/node-20-blue)](https://nodejs.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## 是什么

Butler v5 当前提供：

- 微信 iLink 原生文本、图片、文件和语音入站，文本/图片/文件出站；
- 稳定 conversation stream、多轮上下文与摘要压缩；
- AgentKernel 驱动的 LLM + 结构化工具循环；
- 工作区文件读取、具名命令执行和文件回传；
- 子代理委派、PostgreSQL Outbox 与 WebSocket 异步推送；
- PostgreSQL Event Store 生产持久化，PGlite 测试隔离；
- 多 Provider LLM 与失败降级。

目标设计见 [Butler v5 DESIGN](butler-v5/DESIGN.md)；生产调用链、已实现能力和已知缺口见 [v5 production architecture](docs/architecture/v5-production-architecture-2026-08.md)。

---

## 核心能力

| 能力           | 生产实现                                                             |
| -------------- | -------------------------------------------------------------------- |
| **微信**       | `apps/api/ilink-poller` + `packages/adapters/wechat`                 |
| **Agent Loop** | `apps/api/wechat-inbound-butler` + `packages/runtime/AgentKernel`    |
| **工具**       | 历史、时间、摘要、文件读取、受限命令、微信文件发送、委派             |
| **委派**       | transactional outbox + subagent worker + WS push                     |
| **记忆**       | conversation event history + LLM/extractive compaction               |
| **数据**       | PostgreSQL Event Store / Outbox / Snapshot / Projection；测试 PGlite |
| **扩展边界**   | Channel、MCP、浏览器、调度均按 Policy/ScopedGrant/Sandbox 条件准入   |

---

## 不是什么

Butler 不做多租户 SaaS、公开插件 Marketplace、Kubernetes 默认部署、无限制 shell、宿主机全桌面控制或浏览器端第二套 Loop。

但 MCP、隔离浏览器、本地控制面、多 Channel、定时自治和可观测不再整类否决；它们按“默认关闭、具名范围、短期 ScopedGrant、风险动作即时审批、沙箱与审计”条件准入。唯一边界入口见 [v5 product boundaries](docs/plans/decisions/v5-product-boundaries-2026-08.md)。

---

## 架构一览

```
Owner ──→ 微信 iLink / CLI / HTTP / WebSocket
                         │
                         ▼
                  apps/api delivery shell
                         │
                         ▼
                runtime AgentKernel / EventBridge
                   │                    │
                   ▼                    ▼
             LLM/WeChat adapters      persistence
                                           │
                                           ▼
                                PostgreSQL Event Store
```

目标架构：[Butler v5 DESIGN](butler-v5/DESIGN.md) · 当前实现：[v5 production architecture](docs/architecture/v5-production-architecture-2026-08.md) · 历史迁移：[ADR-0001](docs/adr/2026-08-08-v4-to-v5-supersession.md)

---

## 快速开始

### 1. 安装

```bash
git clone https://github.com/XiaZiHunDun/WFXM.git
cd WFXM
cd butler-v5
pnpm install
```

### 2. 配置

```bash
cp .env.example .env
# 至少配置一个 LLM API Key。
# 原生微信另需 BUTLER_V5_ILINK_ENABLED=1 与 WECHAT_TOKEN。
```

示例：[butler-v5/.env.example](butler-v5/.env.example)

### 3. 运行

```bash
# 开发运行
pnpm --filter @butler/cli exec tsx src/index.ts start

# 微信 QR 登录
pnpm --filter @butler/cli exec tsx src/index.ts wechat-login

# 生产
systemctl --user status butler-v5-gateway.service
```

### 4. 验证

```bash
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
bash scripts/typecheck-gate.sh
```

---

## 当前操作面

- `GET /healthz`：服务健康；
- `POST /v1/wechat/inbound`：微信/测试入站；
- `POST /v1/ws/subscribe` + WebSocket：异步子代理结果；
- `butler start`：启动 API、WS、worker 与可选 iLink poller；
- `butler wechat-login`：iLink QR 登录并写入本地 env。

---

## 仓库结构

```
butler-v5/
├── apps/api/              HTTP、WS、iLink poller、Loop、工具与 worker
├── cli/                   start、wechat-login
├── packages/runtime/      AgentKernel、EventBridge、Decision、Delegate
├── packages/adapters/     LLM、WeChat 与外部协议
├── packages/persistence/  Event Store、Outbox、Snapshot、Projection
├── packages/domain/       纯类型与策略（按生产需求接入）
└── scripts/cutover/       systemd、mock 与 E2E

butler/                    已退役 v4，只读历史参考
docs/                      架构、决策与路线图
```

---

## 文档导航

| 读者              | 从这里开始                                                                                                                     |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **新用户 / 运维** | [v5 handoff](docs/architecture/v5-r10-handoff.md)                                                                              |
| **开发者**        | [AGENTS.md](AGENTS.md) → [目标架构](butler-v5/DESIGN.md) → [当前实现](docs/architecture/v5-production-architecture-2026-08.md) |
| **提需求 / 边界** | [v5 product boundaries](docs/plans/decisions/v5-product-boundaries-2026-08.md)                                                 |
| **后续路线**      | [post-boundary roadmap](docs/plans/active/v5-post-boundary-roadmap-2026-08.md)                                                 |
| **文档体系**      | [DOCUMENTATION.md](docs/DOCUMENTATION.md)                                                                                      |

---

## 参与开发

- 改 `butler-v5` 前请读 [AGENTS.md](AGENTS.md) 与 v5 本地规则
- 贡献约定：[CONTRIBUTING.md](CONTRIBUTING.md)
- Cursor 规则：`.cursor/rules/`

---

## License

MIT — 见 [LICENSE](LICENSE)。

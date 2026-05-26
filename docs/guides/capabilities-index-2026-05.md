# 项目状态总览（已实现 / 未实现 / 依赖）

> **更新**：2026-05-26  
> **用途**：作为维护者总入口，快速判断 Butler 当前哪些能力已实现、哪些仍未实现或明确不做、当前已引入哪些依赖、哪些依赖明确不引入。  
> **原则**：本页只做**路由与摘要**，不替代架构、决策与配置 SSOT。  
> **勿从对照报告正文抽待办** — [`roadmap-backlog`](../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md)

## 0. 图例

- `已落地`：当前仓库已实现并有入口文档 / 守门
- `已落地子集`：已有核心子集，但不是外部产品的全量对标
- `可选`：已实现，但需要 extra、env 或开关启用
- `明确不做`：当前产品边界下不立项
- `可选 Backlog`：可单独立项，但未承诺排期

## 1. 当前能力速览

| 能力 | 当前状态 | 默认 / 可选 | 速查 |
|------|----------|-------------|------|
| 自建 Agent Loop、工具批次、上下文压缩 | 已落地 | 默认 | [`../architecture/v4-architecture.md`](../architecture/v4-architecture.md) |
| 微信 Gateway、入站队列、补充回复、完成推送 | 已落地 | 默认 | [`wechat-gateway-ops.md`](./wechat-gateway-ops.md) |
| Workflow、人工门控、权限控制 | 已落地 | 默认 | [`../config/reference.md`](../config/reference.md) |
| Runtime 指标、`/诊断`、用量与健康快照 | 已落地 | 默认 | [`../ops/diagnostic-thresholds.md`](../ops/diagnostic-thresholds.md) |
| MEMORY、语义检索、Markdown chunking、RAG fallback | 已落地子集 | 默认 | [`four-reports-capabilities-2026-05.md`](./four-reports-capabilities-2026-05.md) |
| Observation Store、durable outbox 等本地状态深化 | 已落地子集 | `durable outbox` 默认；observation queue 需开关 | [`../architecture/v4-architecture.md`](../architecture/v4-architecture.md) |
| MCP 薄客户端 | 已落地 | 可选（extra + 开关） | [`dependency-policy-2026-05.md`](./dependency-policy-2026-05.md) |
| 语音 / OCR / PTY | 已落地 | 可选（extra） | [`dependency-policy-2026-05.md`](./dependency-policy-2026-05.md) |
| 浏览器自动化平台、RAGFlow 全栈、LangGraph 替代 Loop | 明确不做 | 不引入 | [`../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md`](../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md) §1 |

## 2. 已实现能力（文档入口）

| 主线 | 速查文档 | 典型守门 |
|------|----------|----------|
| CC 线束 P0–P4 | [`cc-butler-gap-analysis`](../plans/active/cc-butler-gap-analysis-2026-05.md) | `test_cc_p3_p4_features.py` |
| 四报告 PR1–PR6 | [`four-reports-capabilities`](./four-reports-capabilities-2026-05.md) | `test_ragflow_p0_retrieval` 等 |
| 五报告 PR-F + P5–P10 | [`five-reports-capabilities`](./five-reports-capabilities-2026-05.md) · [`external-agent-reports-capabilities`](./external-agent-reports-capabilities-2026-05.md) | `butler-five-reports-gate.sh` |
| 外部 Agent PR-X | [`external-agent-reports-improvement-roadmap`](../plans/roadmaps/external-agent-reports-improvement-roadmap-2026-05.md) §10 | `test_external_agent_*.py` |
| 外部对标 A/B/C | [`phase-abc-external-reference`](./phase-abc-external-reference.md) | `test_phase_a/b/c_external.py` |
| OpenCode | [`opencode-parity`](./opencode-parity.md) | `test_opencode_*` |
| 运行指标 | [`diagnostic-thresholds`](../ops/diagnostic-thresholds.md) | `test_runtime_metrics.py` |
| MCP 薄客户端 | [`butler-mcp-capability`](../plans/comparisons/butler-mcp-capability-2026-05.md) | `BUTLER_MCP_ENABLED` |

补充事实源：

- 当前模块与架构：[`../architecture/v4-architecture.md`](../architecture/v4-architecture.md)
- 当前 `BUTLER_*` / 默认值：[`../config/reference.md`](../config/reference.md) + [`.env.example`](../../.env.example)
- 已落地总表：[`../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md`](../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md) §4

## 3. 状态判断入口（未对齐 / 明确不做 / 可选 Backlog）

| 类别 | 权威文档 | 用途 |
|------|----------|------|
| 明确不做（总入口） | [`roadmap-backlog-and-boundaries-2026-05.md`](../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md) §1 | 统一否决入口 |
| 报告写“未做”但已有子集 | [`roadmap-backlog-and-boundaries-2026-05.md`](../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md) §2 | 防止把已实现能力误报为缺失 |
| 可选 Backlog | [`roadmap-backlog-and-boundaries-2026-05.md`](../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md) §3 | 可单独立项的剩余项 |
| 四报告 18 项不做 | [`four-reports-out-of-scope-2026-05.md`](../plans/decisions/four-reports-out-of-scope-2026-05.md) | 四报告权威否决正文 |
| 五报告 S1–S11 | [`five-reports-not-done-2026-05.md`](../plans/decisions/five-reports-not-done-2026-05.md) | 五报告不做与 P5–P10 批次 |
| 外部对标 defer | [`external-reference-deferred-2026-05.md`](./external-reference-deferred-2026-05.md) | Hermes/LangChain/Dify/Langflow 的补做与不做 |
| 产品运营 backlog | [`post-consolidation-roadmap-2026-05.md`](../plans/active/post-consolidation-roadmap-2026-05.md) | 与对标主线正交的后续规划 |

一句话判断：

- 想知道“是不是没做”先看 `roadmap-backlog` §2  
- 想知道“是不是明确不做”先看 `roadmap-backlog` §1  
- 想知道“能不能排期”先看 `roadmap-backlog` §3

同一主题域可能同时出现三种状态，典型如 RAG：

- 轻量检索 / chunking / fallback / 子 query 子集：**已落地子集**
- 全量 ingest 管线：**可选 Backlog**
- RAGFlow 全栈 / Studio / 重中间件：**明确不做**

## 4. 已引入依赖

| 类别 | 权威文档 | 说明 |
|------|----------|------|
| core 默认依赖 | [`../../pyproject.toml`](../../pyproject.toml) | `pip install -e .` 会安装的 17 个主路径依赖 |
| optional extras | [`dependency-policy-2026-05.md`](./dependency-policy-2026-05.md) | `[wechat]`、`[mcp]`、`[voice]`、`[wechat-ocr]`、`[cli]`、`[pty]`、`[dev]` |
| 安装方式与分层原则 | [`../config/reference.md`](../config/reference.md) §安装与依赖分层 | `core` vs `optional-dependencies` 的安装入口 |
| 架构原则 | [`../architecture/v4-architecture.md`](../architecture/v4-architecture.md) §依赖分层与本地状态原则 | 为什么这些依赖在 core 或 optional |

当前规则：

- `core` 保持最小：Loop / Transport / 配置 / 本地状态主路径必需
- 微信、MCP、OCR、voice、PTY 等能力优先走 `optional-dependencies`
- `all` 是便捷安装集合，但**不包含** `mcp`

## 5. 明确不引入的依赖

| 类别 | 权威文档 | 代表项 |
|------|----------|--------|
| 平台型重依赖 | [`dependency-policy-2026-05.md`](./dependency-policy-2026-05.md) | Effect、Electron、全量 MCP Host |
| 重基础设施 / Broker | [`roadmap-backlog-and-boundaries-2026-05.md`](../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md) §2.4 | Redis、Postgres、Kafka、RabbitMQ、NATS |
| 对标阶段明确不做 | [`external-reference-deferred-2026-05.md`](./external-reference-deferred-2026-05.md) §3 | LangGraph 替换 Loop、Dify GraphEngine、平台化浏览器 |
| 四报告权威否决 | [`four-reports-out-of-scope-2026-05.md`](../plans/decisions/four-reports-out-of-scope-2026-05.md) | CDP/browser-use、RAGFlow 全栈、Playwright 农场 |
| 五报告权威否决 | [`five-reports-not-done-2026-05.md`](../plans/decisions/five-reports-not-done-2026-05.md) | Bun Worker + Chroma MCP、LangGraph checkpoint 等 |

一句话原则：**能用 JSONL / SQLite / 文件状态解决的，不上平台型基础设施；能放 optional extra 的，不进 core。**

## 6. 推荐阅读顺序

1. [`../architecture/v4-architecture.md`](../architecture/v4-architecture.md)  
2. [`../config/reference.md`](../config/reference.md) + [`.env.example`](../../.env.example)  
3. [`../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md`](../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md)  
4. [`dependency-policy-2026-05.md`](./dependency-policy-2026-05.md)  
5. 对应 `*-capabilities-2026-05.md`

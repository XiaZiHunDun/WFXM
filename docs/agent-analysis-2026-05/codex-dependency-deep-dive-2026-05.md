# Codex 依赖深挖与 Butler 提炼建议

> 范围：`reference/codex/`（重点 `reference/codex/codex-rs/`）  
> 目的：梳理 Codex 的真实依赖与基础设施面，并判断哪些机制值得 Butler 提炼吸收  
> 说明：本文件是分析材料，不代表已经实施；Butler 架构与产品边界仍以 `docs/architecture/v4-architecture.md` 与 `docs/plans/decisions/roadmap-backlog-and-boundaries-2026-05.md` 为准。

## 结论摘要

Codex 不是一个“薄 CLI + 少量脚本”的项目，而是一个以 Rust 为核心的本地 Agent 平台。它的主实现集中在 `reference/codex/codex-rs/`，外围的 `codex-cli/`、`sdk/python/`、`sdk/typescript/` 都更像包装层或接入层。

从依赖和实现看，Codex 最值得 Butler 学习的不是某个单独库，而是三类机制：

1. **本地状态建模**：`JSONL + SQLite` 双轨持久化，而不是单纯选其一。
2. **策略控制面**：权限、命令审批、网络访问、MCP、沙箱配置都收敛为一组可组合策略。
3. **阶段化管线**：记忆、会话、查询索引、事件流都有明确的运行边界，而不是散在各处。

同时也要看到，Codex 并没有依赖很多常被误判的大件：没有 `Redis`、`Kafka`、`RabbitMQ`、`Postgres`、`Celery`、`LangGraph`、`LangChain`、向量数据库、分布式任务队列。这说明它的强项主要来自**本地运行时设计**，而不是重型基础设施。

## 1. Codex 的实现外形

### 1.1 代码组织

- `reference/codex/codex-rs/`：主实现，Cargo workspace，包含 100+ crate。
- `reference/codex/codex-cli/`：Node 启动器，负责分发/启动，不是主业务实现。
- `reference/codex/sdk/python/`：Python SDK，核心依赖是 `pydantic` 和固定版本的 `openai-codex-cli-bin`。
- `reference/codex/sdk/typescript/`：TypeScript SDK，通过 CLI / app-server 对接 Codex。

`reference/codex/codex-rs/README.md` 明确指出 Rust CLI 是维护中的默认实现，并强调其目标是 **standalone executable / zero-dependency install**。

### 1.2 核心运行时依赖

从 `reference/codex/codex-rs/Cargo.toml` 与 `reference/codex/codex-rs/core/Cargo.toml` 看，核心依赖面大致是：

- 异步/系统：`tokio`、`futures`、`portable-pty`
- 网络/协议：`reqwest`、`eventsource-stream`、`tokio-tungstenite`、`axum`
- 配置/序列化：`serde`、`serde_json`、`toml`
- 本地状态：`sqlx`（SQLite）
- 检索与匹配：`bm25`、`globset`、`ignore`、`nucleo`
- 观测：`tracing`、`opentelemetry`
- 安全/认证：`keyring`、`oauth2`、`age`、`aws-config`
- 终端/UI：`ratatui`、`crossterm`
- MCP：`rmcp`

## 2. 依赖与基础设施剖面

### 2.1 数据库与本地存储

Codex 的核心存储不是外部数据库，而是本地状态层：

- `reference/codex/codex-rs/state/`
  - 依赖：`sqlx`
  - 作用：SQLite 状态库，承接 thread metadata、memory job、logs、goals 等查询型状态。
- `reference/codex/codex-rs/rollout/`
  - 作用：会话/线程历史的 JSONL 持久化。
- `reference/codex/codex-rs/thread-store/`
  - 作用：线程存储边界。
  - `thread-store/README.md` 明确：`LocalThreadStore` 用 JSONL 保存 history，用 SQLite 保存 queryable metadata。
- `reference/codex/codex-rs/agent-graph-store/`
  - 作用：agent / thread 关系图，也复用 `codex-state`。

这里最关键的设计不是 SQLite 本身，而是：

- **JSONL 是可回放事实源**
- **SQLite 是查询索引和协调状态**

这和“全量 SQL 会话库替代 transcript”不是一回事。

### 2.2 记忆与检索

Codex 的 memory 线很有代表性：

- `reference/codex/codex-rs/memories/README.md`
  - 明确是 **Phase 1 / Phase 2** 两阶段：
    - Phase 1：从 rollout 中提取结构化 memory，写回 state DB
    - Phase 2：把阶段结果同步到本地 memories 工作区，再跑 consolidation agent
- `reference/codex/codex-rs/memories/write/`
  - 有 workspace diff、prompt 模板、consolidation 等完整链路
- `reference/codex/codex-rs/core/`
  - 引入 `bm25`，说明工具/候选选择不是单纯靠硬编码顺序
- `reference/codex/codex-rs/file-search/`
  - 使用 `ignore` + `nucleo` 做 fuzzy file search

这条线的关键不是“用了什么向量库”，而是它**没有**引入向量数据库，主要靠：

- 本地阶段化提炼
- 本地文件 memory 工件
- BM25 / fuzzy / metadata 过滤

### 2.3 模型、协议与接入层

- `reference/codex/codex-rs/codex-api/`
  - 对 Responses API 的 typed client
  - 负责请求/响应模型、SSE 解析、provider config、auth header、retry tuning
- `reference/codex/codex-rs/app-server/`
  - 本地 `JSON-RPC 2.0` 服务
  - 为 IDE / rich client 提供线程、turn、item、command、fs、skills、hooks、MCP 等接口
- `reference/codex/codex-rs/protocol/`
  - 内外共享协议类型
- `reference/codex/codex-rs/rmcp-client/`
  - MCP 客户端，支持 stdio / child process / streamable-http

所以 Codex 的协议层不是单一 CLI，而是：

- Responses API
- app-server JSON-RPC
- MCP client/server
- 本地事件流

### 2.4 执行、安全与中间件

- `reference/codex/codex-rs/execpolicy/`
  - 规则语义是 `prefix_rule(...)` / `host_executable(...)`
  - 本质上是命令级策略 DSL
- `reference/codex/codex-rs/linux-sandbox/`
  - Linux 下主要走 `bubblewrap`
- `reference/codex/codex-rs/sandboxing/`
  - 统一抽象不同平台沙箱
- `reference/codex/codex-rs/network-proxy/`
  - 本地 HTTP / SOCKS5 策略代理
  - 支持 allowlist / denylist / limited mode / MITM hook
- `reference/codex/codex-rs/login/`、`keyring-store/`、`secrets/`、`aws-auth/`
  - 分别覆盖 OAuth、系统密钥环、加密/脱敏、AWS 认证

这里最有价值的不是把所有安全件照搬，而是它把以下几个面拆开并联动：

- sandbox
- execpolicy
- permission profile
- network policy
- auth / keyring

### 2.5 观测与产品运行信息

- `reference/codex/codex-rs/otel/`
  - `OpenTelemetry` provider、session telemetry、metrics
- `reference/codex/codex-rs/feedback/`
  - Sentry 反馈/错误
- 全局使用 `tracing`

但要注意：这是一套 Codex 自己的产品观测体系，不意味着 Butler 需要默认接入 OTEL/APM。

## 3. 明确没有引入的大件

为了避免误判，这里单列“不在 Codex 主线上”的依赖/平台：

- 没有 `Redis`
- 没有 `Kafka`
- 没有 `RabbitMQ`
- 没有 `Postgres`
- 没有 `Celery`
- 没有 `LangGraph`
- 没有 `LangChain`
- 没有向量数据库（如 Chroma / Qdrant / Milvus / Pinecone）
- 没有多租户 SaaS 消息总线
- 没有全量 MCP Host 平台

这也是为什么 Codex 的经验对 Butler 的价值主要在“机制”，而不是“照搬依赖栈”。

## 4. 对 Butler 最有价值的提炼点

结合 `docs/architecture/v4-architecture.md`、`docs/plans/decisions/roadmap-backlog-and-boundaries-2026-05.md`、以及当前 Butler 代码现状，Codex 里最值得继续提炼的是下面四类。

### 4.1 把 `JSONL + SQLite` 双轨模型做完整

Butler 当前已经有：

- `butler/core/session_transcript.py`：`transcript.jsonl`
- `butler/memory/observation_store.py`：workspace `.butler/observations.db`

这说明方向已经和 Codex 对齐了一半。下一步最值得做的是：

- transcript 派生索引/读模型继续补强
- session / delegate / workflow lineage 查询层
- observation store 的 retention / TTL / flush / workspace 分片收口

这条线与现有边界一致，因为决策文档已经明确：

- 不做 “SQL 消息库替换 `transcript.jsonl`”
- 可以继续增强 `observations.db`

### 4.2 把 memory 线做成清晰的阶段化管线

Butler 当前 memory 线的基础已经不弱：

- `butler/memory/recall_layers.py`
- `butler/memory/semantic_index.py`
- `butler/memory/observer_queue.py`
- `butler/core/preread_context.py`

但和 Codex 相比，差距主要在运行边界而不在单点能力：

- claim / lease / backoff
- bounded batch
- stage outputs
- consolidation
- “先提炼，再合并，再注入”的稳定链路

因此最该学的是 **Phase 化 memory orchestration**，不是 Codex 的 Rust crate 结构本身。

### 4.3 补一层明确的持久化/线程存储 seam

Codex 的 `ThreadStore` / `LiveThread` 值得 Butler 参考。它的意义在于：

- 把 history append 和 metadata patch 分开
- 让 active session 和 cold thread 的路径统一
- 让 fork / resume / archive / search 都落在统一存储边界上

Butler 现在 transcript、workflow、delegate、session 生命周期分散在多处。后续如果要继续增强：

- fork
- child session lineage
- transcript recall
- workflow checkpoint
- run snapshot

很适合补一个轻量统一 seam，而不是继续散落在多个模块里演进。

### 4.4 继续统一策略控制面

Butler 现在已有不少对应能力：

- `butler/permissions.py`
- `butler/execpolicy/`
- `butler/human_gate.py`
- `butler/tools/registry.py`
- MCP allowlist / catalog / deferred tools

Codex 这边最值得继续学的是“策略组合方式”：

- terminal 规则
- external directory
- workflow step allowlist
- approval cache
- MCP server policy
- host / network allowlist

也就是把策略系统做得更一致、更少例外，而不是新增更多独立开关。

## 5. 不建议从 Codex 继续吸收的部分

结合 Butler 当前产品边界，下列部分应继续明确排除：

- `bubblewrap` / Seatbelt / Windows sandbox 三端重做
- `network-proxy` 的 HTTP/SOCKS5/MITM 全家桶
- OTEL / Sentry 默认主链路化
- `codex app-server` 全量协议面
- plugin marketplace / remote control / cloud tasks
- `V8 code-mode`
- 用 SQLite 全量替换 `transcript.jsonl`

这些都超出了 Butler 当前的微信单网关、本地 Python 主线、薄 MCP 边界。

## 6. 对 Butler 的建议优先级

如果把 Codex 深挖的结果转成 Butler 后续优化顺序，我建议：

### P0

1. 收口 observation store 残留项
2. 补 transcript 的派生查询/索引能力
3. 统一 permissions / execpolicy / workflow step 的策略语义

### P1

1. 把 memory 线整理成更明确的阶段化流水线
2. 给 delegate / workflow / fork 增加更稳定的 lineage / snapshot / query 面

### P2

1. 再评估是否需要更强的 item event / app-server 式外部接口层
2. 再评估是否需要更细粒度的 backpressure / overloaded 语义

## 7. 一句话判断

Codex 真正值得 Butler 提炼的，不是 Rust 技术栈，也不是重基础设施，而是：

**本地状态双轨模型 + 一致的策略控制面 + 阶段化 memory 管线。**

保持 Butler 现有的 Python / 微信 / 薄 MCP / `transcript.jsonl` 主线不变，只吸收这些运行时机制，ROI 会更高，也更符合当前产品边界。

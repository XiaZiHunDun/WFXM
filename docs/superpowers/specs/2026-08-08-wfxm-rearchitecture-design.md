# WFXM v5 全面替代架构设计规格

> **文档日期**：2026-08-08  
> **状态**：已完成交互式设计，等待规格文件审阅  
> **目标**：以 Butler v5 全面替代 Butler v4，保留 v4 核心资产，允许用户交互、配置和 API 进行破坏性升级  
> **部署目标**：单机自托管；Docker Compose + PostgreSQL（含 pgvector）  
> **架构基线**：模块化单体 + 事件驱动内核 + 可演进 Port/Plugin 边界

---

## 1. 决策摘要

### 1.1 已确认决策

| 决策项 | 决策 |
|--------|------|
| 终局 | Butler v5 全面替代 v4 |
| v4 角色 | 迁移期 legacy runtime；v5 切换后只读归档 |
| 兼容性 | 允许破坏性升级；不要求保留 v4 命令、配置和 API 表面 |
| 部署 | 单机自托管，不以多租户/Kubernetes 为第一阶段目标 |
| 数据迁移 | 迁移项目、记忆、任务、审批、Skill 元数据和经验等核心资产；旧会话与派生索引离线归档或重建 |
| 组织方式 | 强边界模块化单体，不直接拆网络微服务 |
| 核心范式 | Functional Core / Imperative Shell、ADT、Effect、CQRS、Event Sourcing |
| 主存储 | PostgreSQL Event Store + Projection + Outbox；向量使用 pgvector |
| 扩展策略 | Port/Contract 先行；插件边界保留，但动态插件运行时不进入首个生产切片 |
| 迁移策略 | Strangler + Shadow + Cutover，不采用大爆炸重写 |

### 1.2 一句话架构

> v5 是一个以纯领域模型为核心、以 Effect Port 连接副作用、以 PostgreSQL 事件流为事实源、以 AgentKernel 驱动模型/工具/委派运行、以 Capability Lease 约束权限、以 Compose 部署的事件驱动模块化单体。

---

## 2. 背景与问题

当前 WFXM 的 Butler v4 已具备完整产品能力，但代码库呈现出大型模块化单体、兼容 shim、跨层历史结构和多条架构演进线并存的状态：

- `butler/` 已有 1,490 个 Python 文件，核心能力分布在大量历史模块和兼容路径中；
- Effects、ADT、事件持久化、Tool Registry、验证、Skill、预算和守卫等 WIP 未形成单一可发布边界；
- v4 的文件事实源、SQLite/ChromaDB 派生索引、运行目录和内存状态职责分散；
- `butler-v5/` 已验证 TypeScript + Effect-TS 的 FC/IS、CQRS、Event Sourcing 和 Guard 方向，但尚未正式纳入主线；
- 当前 Python WIP 与 v5 原型并行，使“继续深化 v4”与“正式迁移 v5”缺少明确终局。

本规格不尝试把 v4 的全部文件逐一搬到 v5，而是定义新的领域、运行时、数据和迁移边界。

---

## 3. 目标

### 3.1 产品目标

v5 首个生产版本必须支持：

- 微信文本入站与出站；
- API/CLI 入口；
- 项目创建、激活与 workspace 隔离；
- 多 Provider LLM、fallback 和有限重试；
- Agent 单轮执行；
- 结构化工具调用；
- 文件读取、写入、patch、搜索和受限命令执行；
- Capability Lease、Owner 审批和高风险门控；
- 委派子 Agent；
- 基础 Workflow；
- MEMORY 召回与显式写入；
- 项目任务；
- Event Store、Audit、Outbox、Projection；
- v4 核心资产迁移；
- 诊断、备份、恢复和回滚。

### 3.2 工程目标

- Domain 零 I/O、零基础设施依赖；
- Application 通过 Port 使用所有副作用；
- Apps 只负责协议、认证、生命周期和 UseCase 调用；
- 所有模型输出必须先解码为受限 Decision ADT；
- 重要状态变化可重放、可解释、可审计；
- Projection、Outbox 和 Worker 支持崩溃恢复与幂等；
- 权限越权漏拦截为零；
- 迁移可 dry-run、可重复、可校验、可回滚；
- 将来可以按 Port 拆成服务，但第一阶段不承担网络分布式复杂度。

### 3.3 非目标

首个生产切片不要求：

- 多租户 SaaS；
- Kubernetes 或云原生水平扩展；
- 全量兼容 v4 命令、配置和 API；
- 复刻 v4 的全部 1,490 个 Python 文件和所有历史对标功能；
- OCR、TTS、图片生成等非文本能力；
- 全量 MCP Marketplace；
- 自动经验挖掘和高级 ContextGraph；
- LangGraph、Temporal 或其他重型编排框架；
- 实时把 v5 事件反向迁移成 v4 状态。

---

## 4. 总体架构

```text
┌─────────────────────────────────────────────────────────────┐
│ Apps / Delivery                                               │
│  api · wechat-gateway · worker · cli                          │
└───────────────────────┬─────────────────────────────────────┘
                        │ 只调用 application / runtime
┌───────────────────────▼─────────────────────────────────────┐
│ Runtime Kernel                                                 │
│  AgentKernel · SessionSupervisor · WorkflowRunner              │
│  ToolRuntime · PermissionRuntime · Retry/Supervision · Outbox  │
└───────────────┬───────────────────────────────┬───────────────┘
                │                               │
┌───────────────▼──────────────┐  ┌────────────▼───────────────┐
│ Application                  │  │ Ports / Contracts           │
│ Commands · Queries · UseCases│  │ LLM · EventStore · Memory   │
│ Transaction boundaries       │  │ Tools · Channel · Clock     │
└───────────────┬──────────────┘  │ Secrets · Scheduler · Audit │
                │                 └────────────┬───────────────┘
┌───────────────▼─────────────────────────────▼───────────────┐
│ Domain                                                        │
│ conversation · turn · tools · workflows · projects            │
│ memory · permissions · approvals · events · errors             │
│ pure ADT + deterministic transitions + policies                │
└───────────────────────────────────────────────────────────────┘
                ▲
┌───────────────┴─────────────────────────────────────────────┐
│ Adapters                                                      │
│ PostgreSQL · LLM providers · WeChat iLink · filesystem         │
│ MCP · embeddings · notifications · OpenTelemetry               │
└───────────────────────────────────────────────────────────────┘
```

### 4.1 推荐目录

```text
butler-v5/
├── apps/
│   ├── api/                    # HTTP/Webhook/管理 API
│   ├── wechat-gateway/         # iLink 入站、出站、媒体
│   ├── worker/                 # Outbox、Projection、Scheduler、Memory
│   └── cli/                    # CLI；只依赖 application
├── packages/
│   ├── domain/                 # 零 I/O、零基础设施依赖
│   │   ├── conversation/
│   │   ├── turns/
│   │   ├── tools/
│   │   ├── workflows/
│   │   ├── projects/
│   │   ├── memory/
│   │   ├── permissions/
│   │   ├── approvals/
│   │   ├── events/
│   │   └── errors/
│   ├── application/            # Command/Query 用例与事务编排
│   ├── runtime/                # AgentKernel、会话监督、工具运行时
│   ├── ports/                  # Effect Service/Port 契约
│   ├── adapters/               # 外部系统实现
│   │   ├── postgres/
│   │   ├── llm/
│   │   ├── wechat/
│   │   ├── filesystem/
│   │   ├── mcp/
│   │   └── observability/
│   ├── projections/            # 事件 → 读模型
│   ├── migration/              # v4 核心资产导入与校验
│   ├── config/                 # 单一 Schema 与 profile
│   ├── contracts/              # API/Event/Plugin schema
│   └── shared/                 # 极少量无领域语义工具
├── migrations/                 # PostgreSQL schema
├── tests/
│   ├── domain/
│   ├── application/
│   ├── runtime/
│   ├── adapters/
│   ├── contracts/
│   ├── migration/
│   └── architecture/
└── compose.yaml
```

### 4.2 硬边界

1. `domain` 不依赖 Effect、数据库、HTTP、WeChat、Node 文件系统或具体 LLM SDK；
2. `application` 不直接 import `adapters`；
3. `apps` 不承载业务逻辑；
4. `runtime` 不定义领域规则，只负责执行、监督、并发、取消、重试和预算；其中 `PermissionRuntime` 只负责调用 `domain` 的纯 `PolicyEngine` 并管理 Capability Lease 生命周期；
5. Event Store 是事实源，Projection 是可重建读模型；
6. 依赖只能向内：`apps → runtime/application → ports → domain`，`adapters → ports/domain`；
7. 禁止 `domain → 外层` 和 `application → adapters`。

---

## 5. 领域模型

### 5.1 领域上下文

```text
Project        项目与 workspace 生命周期
Conversation   会话、消息、轮次
Tools          工具定义、调用、结果
Workflow       工作流、委派、步骤状态
Memory         记忆、经验、来源、置信度
Permissions    权限策略、审批、Owner 决策
Operations     领域级任务状态、诊断和运行事件
```

跨上下文只允许通过 Application UseCase 或 Domain Event 交互，禁止任意双向 import。

### 5.2 聚合

| 聚合 | 一致性边界 | 关键状态 |
|------|------------|----------|
| `Project` | 项目配置、workspace、激活 | active / archived / blocked |
| `Conversation` | 会话与轮次顺序 | open / running / waiting / completed |
| `WorkflowRun` | 委派/工作流步骤 | pending / running / waiting_approval / failed / completed |
| `ApprovalRequest` | 一次权限决策 | pending / granted / denied / expired / revoked |
| `MemoryRecord` | 一条可追溯记忆 | candidate / accepted / rejected / expired |
| `Task` | 项目待办与运行任务 | open / claimed / in_progress / blocked / done |

以下不是领域聚合：LLM client、Tool Registry 内存缓存、embedding index、runtime fiber、prompt cache 和 metrics。

### 5.3 Application UseCase

Application 层只暴露明确用例：

```text
StartConversation
SubmitUserMessage
RunTurn
ApproveRequest
RejectRequest
StartWorkflow
ResumeWorkflow
DelegateTask
AcceptMemory
SearchProjectKnowledge
ActivateProject
ImportV4Assets
RebuildProjection
```

每个 UseCase 必须明确输入 schema、读取聚合、允许产生的事件、需要的 Port、同步/异步边界、重试范围、权限要求、幂等 key 和输出模型。

---

## 6. Agent Runtime

### 6.1 模型输出边界

LLM 是不可信的规划器，不是副作用执行器：

```text
LLM Provider
  → Raw Model Response
  → Schema Decoder
  → ModelDecision ADT
  → Policy Engine
  → Application / ToolRuntime
  → 副作用
```

```typescript
type ModelDecision =
  | { readonly _tag: 'Respond'; readonly content: string }
  | { readonly _tag: 'CallTool'; readonly toolName: string; readonly arguments: Readonly<Record<string, unknown>>; readonly callId: string }
  | { readonly _tag: 'Delegate'; readonly role: AgentRole; readonly task: string; readonly capabilities: ReadonlyArray<Capability> }
  | { readonly _tag: 'AskApproval'; readonly request: ApprovalRequestInput }
  | { readonly _tag: 'Finish'; readonly reason: FinishReason }
```

不能解析的模型输出进入 bounded repair/retry；无法修复时产生 `ModelOutputRejected`。

LLM 不能直接访问数据库、文件、微信、权限提升接口、长期记忆或 Guard bypass。

### 6.2 AgentKernel

```text
AgentKernel
├── TurnRunner
├── ContextManager
├── ModelRouter
├── DecisionDecoder
├── PolicyEngine
├── ToolRuntime
├── DelegateRuntime
├── MemoryRuntime
└── EventRecorder
```

`AgentKernel` 只负责加载聚合、执行 UseCase、追加事件和释放运行上下文，不保存长期业务状态。

### 6.3 单轮状态机

```text
Idle
  → TurnOpened
  → ContextPrepared
  → ModelRequested
  → DecisionDecoded

DecisionDecoded
  ├── Respond       → ResponseProduced → Completed
  ├── CallTool      → PolicyChecked
  │                    ├── Denied → Blocked
  │                    ├── Approval → WaitingApproval
  │                    └── Allowed → ToolExecuting
  │                                  ├── Success → ToolResultRecorded
  │                                  ├── Retryable → ToolRetrying
  │                                  └── Fatal → Failed
  ├── Delegate      → ChildRunCreated → WaitingChild
  ├── AskApproval   → WaitingApproval
  └── Finish        → Completed
```

持久领域状态与瞬时运行状态分离。fiber、stream reader、timeout handle、内存队列不作为持久对象序列化。

---

## 7. 事件流与数据事实源

### 7.1 三类事件

#### Domain Events

用于业务状态变化和重放：

```text
ConversationStarted
TurnOpened
AssistantMessageProduced
ToolInvocationRequested
ToolInvocationCompleted
WorkflowStepAdvanced
ApprovalRequested
ApprovalGranted
ProjectActivated
MemoryAccepted
```

#### Audit Events

用于安全、权限和责任追踪：

```text
PermissionEvaluated
PermissionDenied
OwnerApprovalGranted
ExternalPathAccessRequested
ToolExecutionBlocked
LoadBearingFileChanged
MigrationAssetImported
```

#### Operational Telemetry

用于 latency、token、retry、queue depth、projection lag 等指标。Operational telemetry 不进入领域 Event Store。

### 7.2 Event Envelope

```typescript
interface EventEnvelope {
  readonly eventId: string
  readonly eventType: string
  readonly eventVersion: number
  readonly streamId: string
  readonly streamType: 'conversation' | 'project' | 'workflow' | 'approval' | 'memory'
  readonly streamVersion: number
  readonly occurredAt: string
  readonly causationId: string | null
  readonly correlationId: string
  readonly actor: ActorRef
  readonly payload: unknown
  readonly metadata: EventMetadata
}
```

约束：

- `streamId + streamVersion` 唯一，使用乐观并发控制；
- `eventId` 全局唯一，消费者幂等；
- `correlationId` 贯穿一次用户请求；
- `causationId` 形成因果链；
- 大型工具结果、附件和原始模型响应只保存 blob 引用。

### 7.3 PostgreSQL 主存储

| 数据 | 存储 | 是否事实源 |
|------|------|------------|
| Domain Events | PostgreSQL `event_store` | 是 |
| Audit Events | PostgreSQL `audit_events` | 是 |
| Outbox | PostgreSQL `outbox` | 直到投递成功前是 |
| 聚合快照 | PostgreSQL `snapshots` | 可重建缓存 |
| 会话/项目/任务读模型 | PostgreSQL projection tables | 否 |
| 向量索引 | PostgreSQL + pgvector | 否 |
| 大型结果/附件 | content-addressed blob store | 内容事实 |
| 日志/指标/Trace | OpenTelemetry 或本地运行时 | 运维事实 |
| 密钥 | Secret Provider | 配置事实 |

v5 默认不使用 ChromaDB 作为独立主路径；向量通过 Port 保持可替换性。

### 7.4 Outbox 与 Projection

同一 PostgreSQL 事务中追加领域事件、审计事件、Outbox 消息并更新关键 Projection；外部副作用由 Worker 领取。

```text
事务内：append events + append audit + append outbox + critical projection
事务外：claim → execute → delivered / retry / dead-letter
```

系统不承诺绝对 exactly-once，采用：

> 至少一次投递 + 消费者幂等 + 可观测重试。

---

## 8. 权限、安全与配置

### 8.1 Capability Lease

权限从工具名匹配升级为短期能力租约：

```text
Capability Lease
├── subject: agent / workflow / tool call
├── projectId
├── workspaceRoot
├── allowedTools
├── allowedPaths
├── networkPolicy
├── maxCalls
├── expiresAt
├── approvalFingerprint
└── policyVersion
```

子 Agent 不继承父 Agent 全部权限；能力不能由 LLM 自行扩大；租约过期、取消或撤销后立即失效。

### 8.2 纯 Policy Engine

```text
Policy + RequestContext + Resource → PolicyDecision
```

```typescript
type PolicyDecision =
  | { readonly _tag: 'Allow'; readonly lease: CapabilityLease }
  | { readonly _tag: 'Deny'; readonly reason: DenialReason }
  | { readonly _tag: 'RequireApproval'; readonly request: ApprovalRequestInput }
```

Policy Engine 不执行副作用，不直接读取环境变量；环境变量由 Config Adapter 解析为不可变 `PolicyConfig`。

### 8.3 高风险操作

默认走审批或严格策略：workspace 外写入、删除文件、subprocess、Git push、MCP 安装、承重代码修改、敏感导出、网络访问、权限修改、长期记忆写入和高成本任务。

统一流程：

```text
Normalize → Validate → Policy Evaluate → Allow / Deny / RequireApproval → Lease → Execute → Audit
```

所有入口都必须经过同一 Policy/Application 路径，CLI、MCP、Workflow 和 Admin API 不得绕过门控。

### 8.4 工具沙箱

```text
L0 Domain Policy
L1 Capability Lease
L2 ToolRuntime（argv、超时、结果、取消）
L3 OS Sandbox（bubblewrap / container，可选）
L4 Audit
```

核心 Tool API 使用结构化 `CommandSpec`，不接受未解析的 shell 字符串：

```typescript
interface CommandSpec {
  readonly executable: string
  readonly args: ReadonlyArray<string>
  readonly cwd: WorkspaceId
  readonly timeoutMs: number
  readonly network: 'none' | 'allowlist'
}
```

### 8.5 配置

```text
Environment → Secret Provider → Config Profile → Schema Decode → RuntimeConfig → Layer/Port Injection
```

业务模块禁止直接读取 `process.env`。配置分为基础运行配置、Provider 配置、Secret 和项目策略四类。

### 8.6 Plugin/MCP 信任链

```text
Discover → Manifest Validate → Source Trust → Capability Declaration
→ Static Scan → Owner Approval → Staging Install → Contract Test → Activate
```

第一阶段保留 Plugin Port 和 Manifest Contract，但不实现复杂动态 Marketplace 运行时。

---

## 9. 错误处理与可靠性

### 9.1 统一错误 ADT

```typescript
type ButlerError =
  | DomainError
  | ValidationError
  | PolicyError
  | ApprovalError
  | ToolError
  | ProviderError
  | PersistenceError
  | ProjectionError
  | MigrationError
  | ConfigurationError
  | InfrastructureError
```

每个错误包含 `code`、`retryable`、`userSafeMessage`、`severity`、`operationId`、`correlationId` 和可选 cause。

### 9.2 Supervisor 树

```text
AppSupervisor
├── ApiSupervisor
├── WeChatSupervisor
├── WorkerSupervisor
│   ├── OutboxWorker
│   ├── ProjectionWorker
│   ├── SchedulerWorker
│   └── MemoryWorker
└── HealthSupervisor
```

Worker 必须具备 heartbeat、lease、backoff、有界重启、dead-letter、优雅关闭和恢复后继续领取任务的能力。

### 9.3 错误默认策略

| 错误 | 默认处理 |
|------|----------|
| Schema/参数错误 | 不重试，返回修正提示 |
| 权限拒绝 | 不重试，写 Audit |
| 未审批 | 挂起 Workflow |
| LLM 限流/临时网络 | 有界退避 + Provider fallback |
| 工具超时 | 取消并按策略重试 |
| 数据库瞬态错误 | UseCase/Worker 有界重试 |
| Projection 失败 | 不回滚领域事件，进入重放队列 |
| 迁移校验失败 | 阶段性失败，不提交目标数据 |
| 不可恢复错误 | 标记失败并通知 Owner |

---

## 10. 部署与可观测性

### 10.1 单机 Compose

```text
compose
├── postgres (+ pgvector)
├── api
├── wechat-gateway
├── worker
└── optional otel-collector / local UI
```

三个应用共享代码包但不共享可变内存状态，PostgreSQL 是跨进程协调中心。开发环境可以合并为一个 dev runner，生产环境建议分进程运行。

### 10.2 关联标识

每次用户请求必须创建并贯穿：

```text
correlationId
├── operationId
├── conversationId
├── turnId
├── workflowRunId
├── toolCallId
└── eventId / causationId chain
```

### 10.3 必备指标

- LLM latency、token、fallback；
- tool success/failure/timeout；
- approval wait time；
- workflow retry/dead-letter；
- event append latency；
- projection lag；
- outbox depth；
- memory recall latency；
- context compression ratio；
- migration imported/rejected/warned；
- 安全策略拒绝数。

日志使用结构化 JSON，不记录 API Key、完整 prompt 或敏感文件原文。

---

## 11. 测试策略与 CI 门禁

### 11.1 测试层级

```text
E2E / WeChat
Adapter Integration
Application
Runtime
Domain Pure
```

必须覆盖：

- Domain 状态机、ADT、策略、Projection；
- Application UseCase、事务和事件；
- Runtime fake LLM/fake Tool、取消、超时、重试、预算；
- PostgreSQL、WeChat、LLM、文件适配器；
- Port、Event、API、Plugin Manifest Contract；
- 依赖方向与 Domain 零 I/O；
- v4 fixture 迁移、幂等、hash、拒绝和回滚；
- capability 越权、路径穿越、审批绕过和 MCP 信任；
- API、微信、委派、审批和恢复主流程。

### 11.2 CI Gate

```text
format:check
→ typecheck
→ lint
→ deadcode
→ domain/application tests
→ adapter integration
→ contract tests
→ architecture tests
→ migration tests
→ security guard tests
→ coverage
→ container smoke
```

发布前还需执行 PostgreSQL 备份恢复、Outbox dead-letter、Projection 重建、v4 迁移 dry-run、断电恢复、WeChat 长任务恢复和 Provider 故障切换。

---

## 12. v4 → v5 迁移

### 12.1 迁移资产

| v4 资产 | v5 处理 |
|----------|----------|
| 项目定义/元数据 | `ProjectImported` |
| `MEMORY.md`/项目记忆 | 结构化 Memory records |
| Owner profile/facts | 受信任 Memory records |
| 未完成任务/项目待办 | Task/Workflow records |
| 已批准权限 | 重新校验后生成 Approval Policy |
| Skill 元数据 | Manifest + 重新安全扫描 |
| 经验条目 | Experience records，保留来源/置信度 |
| 旧 session transcript | 离线归档，不进入首期在线状态 |
| ChromaDB/SQLite 索引 | 不直接导入，按 v5 记录重建 |
| 旧日志/指标 | 归档，不进入领域状态 |

### 12.2 迁移流程

```text
scan → dry-run → import staging → validate → commit
```

迁移器必须提供 manifest、输入 hash、统计、警告/拒绝项、幂等 key、失败回滚和导入后 invariant 检查。

---

## 13. 分阶段实施路线

整个重构拆成八个独立子项目，每个子项目分别编写 spec、实现计划、测试和验收报告。

| 阶段 | 子项目 | 交付物 | 退出条件 |
|------|--------|--------|----------|
| R0 | 仓库与决策收口 | v5 分支、ADR、WIP 分类、运行数据隔离 | v4/v5 边界明确 |
| R1 | 工程基线 | lint、typecheck、CI、测试发现、架构门禁 | `pnpm gate` 可信并全绿 |
| R2 | Domain + Contracts | 聚合、ADT、Command/Event/API schema | Domain 零 I/O |
| R3 | Persistence Kernel | Event Store、Audit、Outbox、Projection、Blob | 崩溃恢复/幂等/重放通过 |
| R4 | Agent Runtime | AgentKernel、Decision、Tool、Delegate | fake LLM 完整 Turn/Workflow 通过 |
| R5 | Adapters + Delivery | PostgreSQL、LLM、WeChat、MCP、CLI/API | Compose E2E 通过 |
| R6 | Migration + Shadow | v4 importer、shadow comparison、验收报告 | 核心资产 dry-run 和 shadow 达标 |
| R7 | Cutover + Retirement | 切换、回滚、v4 归档、文档收口 | v5 稳定窗口通过 |

### 13.1 R0 规则

R0 完成前：

- 不继续向 v4 添加新的架构级抽象；
- 不把 `.wfxm_data` 运行数据混入功能提交；
- 不把 v5 原型和 v4 WIP 混成一个提交；
- 明确 v4 只接受 P0 安全/生产修复；
- 修复 worktree Hook 根路径解析。

### 13.2 最小生产切片

首个 v5 生产版本不需要复刻 v4 全部能力，但必须具备：微信文本、API/CLI、项目、LLM fallback、Agent Turn、结构化工具、审批、委派、基础 Workflow、MEMORY、任务、Event Store/Audit/Outbox/Projection、核心资产迁移、诊断和恢复。

### 13.3 Shadow 验收门槛

Shadow 模式接收 v4 脱敏输入，只生成 Decision，不发送微信、不执行写工具、不写长期记忆。

切换前建议满足：

- 核心场景成功率 ≥ 95%；
- 高风险越权漏拦截为 0；
- 核心资产拒绝项全部人工处置；
- 连续 7 天 Shadow 无 P0；
- 关键 E2E、恢复和回滚演练通过。

### 13.4 Cutover

```text
v4 read-only window
→ v4 snapshot
→ final delta import
→ manifest/hash/invariant validation
→ start v5
→ core E2E
→ switch WeChat Gateway
→ observe
→ v5 active
```

### 13.5 Rollback

回滚依赖切换前 v4 快照，不把 v5 事件实时反向迁移为 v4 状态。若触发 P0：停止 v5 外部写入、恢复 v4 Gateway 与快照、导出切换窗口内未安全处理的用户消息、保留 v5 事件用于分析和重新迁移。

---

## 14. 完成定义

只有全部满足以下条件，才称为“v5 全面替代完成”：

- v5 是唯一活动产品主线；
- v4 不再处理生产流量；
- 核心资产迁移报告完整；
- v5 强制门禁全绿；
- Event Store 可重放；
- Projection 可重建；
- PostgreSQL 可备份恢复；
- Outbox 与 dead-letter 可运维；
- 微信主流程和审批流程通过 E2E；
- Provider 故障切换通过；
- 权限绕过测试为 0；
- v4 归档为只读参考；
- README、架构、配置、运维和迁移文档全部以 v5 为 SSOT。

---

## 15. 后续文档拆分

本规格是目标架构总设计，不直接替代实施计划。后续应拆为：

1. R0 仓库收口与 v4/v5 终局 ADR；
2. R1 v5 工程基线与门禁；
3. R2 Domain/Contracts 详细设计；
4. R3 PostgreSQL Event Store/Outbox/Projection 详细设计；
5. R4 AgentKernel/ToolRuntime 详细设计；
6. R5 Adapter 与 Compose 详细设计；
7. R6 v4 核心资产迁移与 Shadow 详细设计；
8. R7 Cutover、Rollback 与 v4 归档 Runbook。

每个子项目独立经过：设计 → 计划 → TDD → 实现 → 验证 → Review。

# Butler v5 — 函数式架构完整重写方案

> **日期**：2026-07-30  
> **定位**：从零设计的新架构，非渐进迁移  
> **核心范式**：函数式核心 + 命令式外壳（FC/IS）  
> **技术栈**：TypeScript + Effect-TS + PostgreSQL + Bun  
> **设计目标**：简洁、可测、类型安全、可组合

---

## 一、为什么重新设计

### 1.1 当前架构的根本问题

当前 Butler v4 的核心问题不是"Python 不够好"，而是**架构范式层面的缺陷**：

| 根本问题 | 表现 | 根因 |
|----------|------|------|
| **副作用与逻辑混杂** | 12,058 个测试需要大量 mock | 没有 FC/IS 分离 |
| **状态不可追踪** | 200+ 全局变量、9 个模块级单例 | 没有事件溯源 |
| **错误处理分散** | try/except 散布在 1,490 个文件 | 没有统一的错误 ADT |
| **模块边界模糊** | core/ 299 文件、core→ops 22 处违规导入 | 没有 Layer 依赖注入 |
| **并发控制脆弱** | 线程锁、全局可变状态 | 没有 Fiber 模型 |
| **配置爆炸** | 200+ BUTLER_* 环境变量 | 没有配置 Schema |

### 1.2 新架构的核心理念

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  纯函数是可测试的     ←→    副作用是可控的                    │
│                                                             │
│  ADT 让非法状态不可表示     Effect 让副作用可组合              │
│                                                             │
│  Event Sourcing 让状态可追溯    Layer 让依赖可替换             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**六条设计原则**：

1. **非法状态不可表示** — 用 ADT（代数数据类型）建模，编译期消除非法状态
2. **纯函数优先** — 业务逻辑零副作用，输入相同→输出相同
3. **副作用显式化** — 所有 I/O 包裹在 Effect 中，类型签名声明依赖
4. **组合优于继承** — 用 pipe/flatMap 组合，不用类继承
5. **错误是值** — 用 Either/Result 表示错误，不用 throw
6. **不可变优先** — 数据用 readonly，状态变更通过事件

---

## 二、技术选型

### 2.1 核心技术栈

| 类别 | 选择 | 版本 | 选择理由 |
|------|------|------|----------|
| **语言** | TypeScript | 5.5+ | 类型系统足够表达 ADT、条件类型、模板字面量 |
| **运行时** | Bun | 1.1+ | 原生 TS 执行、内置测试/打包、比 Node 快 3-4x |
| **函数式框架** | Effect-TS | 3.x | Layer（DI）、Fiber（并发）、Schedule（重试）、Stream（事件流） |
| **数据库** | PostgreSQL | 16+ | 关系型 + pgvector 向量搜索，统一存储 |
| **ORM** | Drizzle ORM | 0.33+ | 类型安全 SQL 构建、零运行时开销、migration 工具 |
| **HTTP 框架** | Hono | 4.x | 轻量、类型安全、Bun 原生支持 |
| **Schema 校验** | Effect Schema | 0.60+ | 与 Effect 深度集成、编译期+运行时双重校验 |
| **包管理** | pnpm | 9+ | workspace、硬链接节省磁盘 |
| **Monorepo** | Turborepo | 2+ | 增量构建、远程缓存、任务编排 |
| **测试** | Bun test | — | 原生集成、零配置、极快 |
| **容器** | Docker + Compose | — | 开发+部署统一环境 |

### 2.2 为什么选 Effect-TS 而非 fp-ts

| 维度 | fp-ts | Effect-TS |
|------|-------|-----------|
| **依赖注入** | ❌ 需手动 Reader Monad | ✅ Layer 原生支持 |
| **并发** | ❌ 需手动 Promise 管理 | ✅ Fiber 模型 |
| **重试** | ❌ 需自己实现 | ✅ Schedule 组合器 |
| **资源管理** | ❌ 需手动 bracket | ✅ acquireRelease/Scope |
| **可观测性** | ❌ 无 | ✅ 内置 tracing/metrics/logging |
| **流处理** | ❌ 需 RxJS | ✅ Stream 原生 |

**结论**：Effect-TS 是 fp-ts 的超集，选择 Effect-TS 意味着不需要 fp-ts。

---

## 三、Monorepo 结构

### 3.1 目录结构

```
butler-v5/
├── apps/                           # 可执行应用（命令式外壳入口）
│   ├── gateway/                    # 微信网关 + HTTP 服务
│   │   ├── src/
│   │   │   ├── index.ts            # 入口：启动 Hono + Bun.serve
│   │   │   ├── routes/             # HTTP 路由
│   │   │   ├── wechat/             # 微信 iLink 适配器
│   │   │   └── runtime.ts          # Effect Runtime 配置
│   │   └── tests/
│   ├── cli/                        # 命令行界面
│   │   ├── src/
│   │   │   ├── index.ts            # 入口
│   │   │   ├── commands/           # butler chat / butler gateway / ...
│   │   │   └── runtime.ts
│   │   └── tests/
│   └── worker/                     # 后台 Worker（Outbox/eval/定时任务）
│       ├── src/
│       │   ├── index.ts
│       │   ├── outbox-worker.ts    # Outbox 事件派发
│       │   ├── eval-worker.ts      # 评估任务
│       │   └── runtime.ts
│       └── tests/
│
├── packages/                       # 可复用包
│   ├── domain/                     # 📦 领域核心（纯函数，零依赖）
│   │   ├── src/
│   │   │   ├── conversation/       # 对话域
│   │   │   │   ├── types.ts        # ADT: LoopState, LoopEvent, Message...
│   │   │   │   ├── transition.ts   # 纯函数: 状态转换
│   │   │   │   ├── logic.ts        # 纯函数: 业务规则
│   │   │   │   └── index.ts
│   │   │   ├── tools/              # 工具域
│   │   │   │   ├── types.ts        # ADT: Tool, ToolCall, ToolResult...
│   │   │   │   ├── schema.ts       # 工具参数 Schema 定义
│   │   │   │   └── index.ts
│   │   │   ├── memory/             # 记忆域
│   │   │   │   ├── types.ts        # ADT: Observation, Recall, Vector...
│   │   │   │   ├── projection.ts   # 纯函数: 读模型投影
│   │   │   │   └── index.ts
│   │   │   ├── projects/           # 项目域
│   │   │   │   ├── types.ts
│   │   │   │   ├── rules.ts        # 纯函数: 项目规则
│   │   │   │   └── index.ts
│   │   │   ├── workflows/          # 工作流域
│   │   │   │   ├── types.ts        # ADT: DAG, Task, WorkflowState...
│   │   │   │   ├── dag.ts          # 纯函数: 拓扑排序、依赖解析
│   │   │   │   └── index.ts
│   │   │   ├── permissions/        # 权限域
│   │   │   │   ├── types.ts        # ADT: Permission, Rule, Decision...
│   │   │   │   ├── policy.ts       # 纯函数: 权限判定
│   │   │   │   └── index.ts
│   │   │   └── errors.ts           # 全局错误 ADT
│   │   ├── tests/                  # 纯函数测试（零 mock）
│   │   │   ├── conversation/
│   │   │   ├── tools/
│   │   │   ├── memory/
│   │   │   └── ...
│   │   └── package.json
│   │
│   ├── application/                 # 📦 应用层（Effect 组合，编排）
│   │   ├── src/
│   │   │   ├── conversation/       # 对话用例
│   │   │   │   ├── run-loop.ts     # Agent Loop 执行（Effect.gen）
│   │   │   │   ├── prepare-context.ts
│   │   │   │   ├── call-llm.ts
│   │   │   │   └── execute-tools.ts
│   │   │   ├── memory/            # 记忆用例
│   │   │   │   ├── store-observation.ts
│   │   │   │   └── recall.ts
│   │   │   ├── tools/             # 工具用例
│   │   │   │   ├── dispatch-tool.ts
│   │   │   │   └── batch-execute.ts
│   │   │   ├── workflows/         # 工作用例
│   │   │   │   ├── run-workflow.ts
│   │   │   │   └── handle-approval.ts
│   │   │   └── projects/          # 项目用例
│   │   │       ├── create-project.ts
│   │   │       └── switch-project.ts
│   │   ├── tests/                 # 用例测试（Mock Layer）
│   │   └── package.json
│   │
│   ├── infrastructure/            # 📦 基础设施（命令式外壳）
│   │   ├── src/
│   │   │   ├── database/          # PostgreSQL 适配
│   │   │   │   ├── schema.ts      # Drizzle 表定义
│   │   │   │   ├── migrations/    # 迁移脚本
│   │   │   │   ├── repositories/  # 仓储实现
│   │   │   │   └── layers.ts      # Database Layer
│   │   │   ├── llm/              # LLM 客户端
│   │   │   │   ├── providers/     # OpenAI/Anthropic/MiniMax...
│   │   │   │   ├── client.ts      # 统一客户端
│   │   │   │   ├── retry.ts       # 重试策略
│   │   │   │   └── layers.ts     # LLM Layer
│   │   │   ├── wechat/           # 微信网关适配
│   │   │   │   ├── ilink/        # iLink 协议
│   │   │   │   ├── inbound.ts     # 入站消息处理
│   │   │   │   ├── outbound.ts    # 出站消息发送
│   │   │   │   └── layers.ts     # WeChat Layer
│   │   │   ├── vector/          # 向量存储
│   │   │   │   ├── pgvector.ts    # pgvector 适配
│   │   │   │   ├── embedding.ts  # 嵌入生成
│   │   │   │   └── layers.ts
│   │   │   ├── eventstore/      # 事件存储
│   │   │   │   ├── postgres-store.ts
│   │   │   │   ├── projections/  # 读模型投影
│   │   │   │   └── layers.ts
│   │   │   ├── cache/           # 缓存
│   │   │   │   ├── lru.ts
│   │   │   │   └── layers.ts
│   │   │   └── observability/  # 可观测性
│   │   │       ├── metrics.ts
│   │   │       ├── tracing.ts
│   │   │       └── layers.ts
│   │   ├── tests/               # 集成测试（真实 DB/HTTP）
│   │   └── package.json
│   │
│   ├── contracts/                # 📦 端口接口（Effect Tags）
│   │   ├── src/
│   │   │   ├── services/        # Service 接口定义
│   │   │   │   ├── llm.ts       # LLMService Tag
│   │   │   │   ├── database.ts  # DatabaseService Tag
│   │   │   │   ├── vector.ts    # VectorService Tag
│   │   │   │   ├── eventstore.ts # EventStoreService Tag
│   │   │   │   ├── wechat.ts    # WeChatService Tag
│   │   │   │   ├── cache.ts     # CacheService Tag
│   │   │   │   └── observability.ts
│   │   │   ├── layers/         # 默认 Layer 组合
│   │   │   │   ├── production.ts
│   │   │   │   ├── development.ts
│   │   │   │   └── test.ts
│   │   │   └── index.ts
│   │   └── package.json
│   │
│   └── shared/                   # 📦 共享工具
│       ├── src/
│       │   ├── types/           # 共享类型
│       │   ├── crypto/         # 哈希/加密
│       │   ├── time/           # 时间工具
│       │   └── utils/          # 通用工具函数
│       └── package.json
│
├── turbo.json                    # Turborepo 配置
├── pnpm-workspace.yaml
├── package.json
├── tsconfig.base.json            # 共享 TS 配置
└── docker-compose.yml            # 开发环境
```

### 3.2 包依赖规则

```
apps/gateway ──→ packages/application ──→ packages/domain
     │                  │                      ↑
     │                  └──→ packages/contracts (Effect Tags)
     │                  └──→ packages/infrastructure (实现)
     └──→ packages/shared
```

**核心规则**：
- `domain/` **零依赖** — 不依赖任何其他包，纯 TypeScript 类型+函数
- `contracts/` 只依赖 `effect` 和 `domain/` — 定义接口，不含实现
- `application/` 依赖 `domain/` + `contracts/` — 用 Effect 组合业务逻辑
- `infrastructure/` 依赖 `contracts/` — 实现 Port 接口
- `apps/` 依赖 `application/` + `infrastructure/` — 组装运行时

**依赖方向是单向的**，不允许循环依赖。

---

## 四、领域模型设计

### 4.1 对话域（Conversation）

这是系统的核心域——Agent Loop。

#### 4.1.1 状态机 ADT

```typescript
// packages/domain/src/conversation/types.ts

// ===== 对话状态（ADT — 非法状态不可表示）=====

export type LoopState =
  | { readonly _tag: "Idle" }
  | { readonly _tag: "Preparing"; readonly input: UserInput; readonly turn: number }
  | { readonly _tag: "CallingLLM"; readonly messages: readonly Message[]; readonly turn: number }
  | { readonly _tag: "ExecutingTools"; readonly pendingCalls: readonly ToolCall[]; readonly turn: number }
  | { readonly _tag: "Compressing"; readonly reason: CompressReason; readonly messages: readonly Message[] }
  | { readonly _tag: "Retrying"; readonly attempt: number; readonly error: RetryableError }
  | { readonly _tag: "Completed"; readonly result: LoopResult }
  | { readonly _tag: "Failed"; readonly error: LoopError }
  | { readonly _tag: "Interrupted"; readonly reason: string }

// ===== 事件（驱动状态转换）=====

export type LoopEvent =
  | { readonly _tag: "UserMessage"; readonly content: string; readonly sessionId: string }
  | { readonly _tag: "ContextReady"; readonly messages: readonly Message[] }
  | { readonly _tag: "LLMResponse"; readonly response: LLMResult; readonly needsTools: boolean }
  | { readonly _tag: "ToolResults"; readonly results: readonly ToolResult[] }
  | { readonly _tag: "ContextOverflow"; readonly tokens: number; readonly limit: number }
  | { readonly _tag: "RetryAttempt"; readonly error: RetryableError }
  | { readonly _tag: "Interrupt"; readonly reason: string }
  | { readonly _tag: "Complete"; readonly response: string }
  | { readonly _tag: "Fail"; readonly error: LoopError }

// ===== 消息类型 =====

export type Message =
  | { readonly _tag: "System"; readonly content: string }
  | { readonly _tag: "User"; readonly content: string }
  | { readonly _tag: "Assistant"; readonly content: string; readonly toolCalls?: readonly ToolCall[] }
  | { readonly _tag: "Tool"; readonly toolCallId: string; readonly content: string }
  | { readonly _tag: "Compacted"; readonly summary: string; readonly originalCount: number }

// ===== 错误 ADT =====

export type LoopError =
  | { readonly _tag: "MaxRetriesExceeded"; readonly attempts: number; readonly lastError: string }
  | { readonly _tag: "AllProvidersFailed"; readonly providers: readonly string[] }
  | { readonly _tag: "ContextTooLarge"; readonly tokens: number; readonly limit: number }
  | { readonly _tag: "ToolExecutionFailed"; readonly tool: string; readonly reason: string }
  | { readonly _tag: "Interrupted"; readonly reason: string }

export type RetryableError =
  | { readonly _tag: "EmptyResponse" }
  | { readonly _tag: "SchemaError"; readonly details: string }
  | { readonly _tag: "RateLimited"; readonly retryAfter: number }
  | { readonly _tag: "ProviderOverloaded"; readonly provider: string }
```

#### 4.1.2 纯函数：状态转换

```typescript
// packages/domain/src/conversation/transition.ts

import type { LoopState, LoopEvent } from "./types"

/**
 * 纯函数：状态转换。
 * 给定当前状态和事件，返回新状态。
 * 无副作用、可测试、确定性。
 */
export const transition = (state: LoopState, event: LoopEvent): LoopState => {
  switch (state._tag) {
    // ===== Idle 状态 =====
    case "Idle": {
      if (event._tag === "UserMessage") {
        return {
          _tag: "Preparing",
          input: { text: event.content, sessionId: event.sessionId },
          turn: 1,
        }
      }
      return state // 忽略不相关事件
    }

    // ===== Preparing 状态 =====
    case "Preparing": {
      switch (event._tag) {
        case "ContextReady":
          return { _tag: "CallingLLM", messages: event.messages, turn: state.turn }
        case "ContextOverflow":
          return { _tag: "Compressing", reason: { tokens: event.tokens, limit: event.limit }, messages: [] }
        case "Interrupt":
          return { _tag: "Interrupted", reason: event.reason }
        default:
          return state
      }
    }

    // ===== CallingLLM 状态 =====
    case "CallingLLM": {
      switch (event._tag) {
        case "LLMResponse": {
          if (event.needsTools) {
            return {
              _tag: "ExecutingTools",
              pendingCalls: event.response.toolCalls ?? [],
              turn: state.turn,
            }
          }
          return { _tag: "Completed", result: { response: event.response.content, turn: state.turn } }
        }
        case "RetryAttempt":
          return { _tag: "Retrying", attempt: 1, error: event.error }
        case "Interrupt":
          return { _tag: "Interrupted", reason: event.reason }
        default:
          return state
      }
    }

    // ===== ExecutingTools 状态 =====
    case "ExecutingTools": {
      if (event._tag === "ToolResults") {
        // 工具执行完毕，回到 LLM 调用
        const newMessages = [...state.messages, ...event.results.map(toToolMessage)]
        return { _tag: "CallingLLM", messages: newMessages, turn: state.turn + 1 }
      }
      if (event._tag === "Interrupt") {
        return { _tag: "Interrupted", reason: event.reason }
      }
      return state
    }

    // ===== Compressing 状态 =====
    case "Compressing": {
      if (event._tag === "ContextReady") {
        return { _tag: "CallingLLM", messages: event.messages, turn: state.turn }
      }
      return state
    }

    // ===== Retrying 状态 =====
    case "Retrying": {
      if (event._tag === "LLMResponse") {
        if (event.needsTools) {
          return { _tag: "ExecutingTools", pendingCalls: event.response.toolCalls ?? [], turn: state.turn }
        }
        return { _tag: "Completed", result: { response: event.response.content, turn: state.turn } }
      }
      if (event._tag === "Fail") {
        return { _tag: "Failed", error: event.error }
      }
      if (event._tag === "RetryAttempt") {
        return { _tag: "Retrying", attempt: state.attempt + 1, error: event.error }
      }
      return state
    }

    // ===== 终态 =====
    case "Completed":
    case "Failed":
    case "Interrupted":
      return state // 终态不可转换
  }
}
```

#### 4.1.3 测试（零 mock）

```typescript
// packages/domain/tests/conversation/transition.test.ts

import { describe, test, expect } from "bun:test"
import { transition } from "../src/conversation/transition"
import type { LoopState, LoopEvent } from "../src/conversation/types"

describe("transition", () => {
  test("Idle + UserMessage → Preparing", () => {
    const state: LoopState = { _tag: "Idle" }
    const event: LoopEvent = { _tag: "UserMessage", content: "hello", sessionId: "s1" }
    
    const next = transition(state, event)
    
    expect(next).toEqual({
      _tag: "Preparing",
      input: { text: "hello", sessionId: "s1" },
      turn: 1,
    })
  })

  test("CallingLLM + LLMResponse(needsTools) → ExecutingTools", () => {
    const state: LoopState = {
      _tag: "CallingLLM",
      messages: [{ _tag: "User", content: "read file" }],
      turn: 1,
    }
    const event: LoopEvent = {
      _tag: "LLMResponse",
      response: { content: "", toolCalls: [{ name: "read_file", args: { path: "/tmp" } }] },
      needsTools: true,
    }
    
    const next = transition(state, event)
    
    expect(next._tag).toBe("ExecutingTools")
  })

  test("终态不可转换", () => {
    const completed: LoopState = { _tag: "Completed", result: { response: "done", turn: 1 } }
    const event: LoopEvent = { _tag: "UserMessage", content: "more", sessionId: "s1" }
    
    const next = transition(completed, event)
    
    expect(next).toBe(completed) // 引用相等
  })
})
```

**这就是函数式架构的核心优势**：状态转换逻辑是纯函数，测试不需要任何 mock，输入相同→输出相同，100% 可预测。

### 4.2 工具域

```typescript
// packages/domain/src/tools/types.ts

// 工具定义 ADT
export type ToolDefinition =
  | { readonly _tag: "ReadFile"; readonly schema: ReadFileSchema }
  | { readonly _tag: "WriteFile"; readonly schema: WriteFileSchema }
  | { readonly _tag: "Patch"; readonly schema: PatchSchema }
  | { readonly _tag: "SearchFiles"; readonly schema: SearchSchema }
  | { readonly _tag: "ListDirectory"; readonly schema: ListDirSchema }
  | { readonly _tag: "ExecuteCommand"; readonly schema: ExecSchema; readonly requiresApproval: boolean }
  | { readonly _tag: "DelegateTask"; readonly schema: DelegateSchema; readonly maxDepth: number }
  | { readonly _tag: "RunWorkflow"; readonly schema: WorkflowSchema }
  | { readonly _tag: "WebFetch"; readonly schema: WebFetchSchema }
  | { readonly _tag: "GitOperation"; readonly schema: GitSchema; readonly requiresApproval: boolean }

// 工具调用结果
export type ToolResult =
  | { readonly _tag: "Success"; readonly content: string; readonly metadata?: ToolMetadata }
  | { readonly _tag: "Failure"; readonly error: ToolError; readonly partialContent?: string }

export type ToolError =
  | { readonly _tag: "NotFound"; readonly resource: string }
  | { readonly _tag: "PermissionDenied"; readonly resource: string; readonly rule: string }
  | { readonly _tag: "ValidationError"; readonly field: string; readonly reason: string }
  | { readonly _tag: "ExecutionError"; readonly reason: string; readonly exitCode?: number }
  | { readonly _tag: "Timeout"; readonly duration: number }
  | { readonly _tag: "Cancelled" }

// 纯函数：验证工具参数
export const validateToolCall = (
  tool: ToolDefinition,
  args: unknown
): ValidationResult => {
  // 纯函数：根据 schema 验证参数
}
```

### 4.3 记忆域（CQRS + Event Sourcing）

```typescript
// packages/domain/src/memory/types.ts

// ===== 事件（写模型）=====
export type MemoryEvent =
  | { readonly _tag: "ObservationStored"; readonly observation: Observation; readonly timestamp: number }
  | { readonly _tag: "ObservationExpired"; readonly id: string }
  | { readonly _tag: "VectorIndexed"; readonly id: string; readonly embedding: readonly number[] }
  | { readonly _tag: "MemoryForgotten"; readonly id: string; readonly reason: string }
  | { readonly _tag: "MemoryReinforced"; readonly id: string; readonly weight: number }

// ===== 命令 =====
export type MemoryCommand =
  | { readonly _tag: "StoreObservation"; readonly observation: Observation }
  | { readonly _tag: "ForgetMemory"; readonly id: string; readonly reason: string }
  | { readonly _tag: "ReinforceMemory"; readonly id: string }

// ===== 查询 =====
export type MemoryQuery =
  | { readonly _tag: "RecallBySemantic"; readonly query: string; readonly limit: number }
  | { readonly _tag: "RecallByTag"; readonly tags: readonly string[] }
  | { readonly _tag: "RecallByTimeRange"; readonly from: number; readonly to: number }

// ===== 读模型（投影）=====
export interface MemoryReadModel {
  readonly observations: ReadonlyMap<string, Observation>
  readonly vectorIndex: VectorIndex
  readonly tagIndex: ReadonlyMap<string, readonly string[]>
}

// ===== 纯函数：从事件重建读模型 =====
export const rebuildReadModel = (events: readonly MemoryEvent[]): MemoryReadModel => {
  let observations = new Map<string, Observation>()
  let vectorIndex = new VectorIndex()
  let tagIndex = new Map<string, string[]>()

  for (const event of events) {
    switch (event._tag) {
      case "ObservationStored":
        observations.set(event.observation.id, event.observation)
        for (const tag of event.observation.tags) {
          const existing = tagIndex.get(tag) ?? []
          tagIndex.set(tag, [...existing, event.observation.id])
        }
        break
      case "VectorIndexed":
        vectorIndex.add(event.id, event.embedding)
        break
      case "ObservationExpired":
      case "MemoryForgotten":
        observations.delete(event.id)
        vectorIndex.remove(event.id)
        break
      case "MemoryReinforced":
        // 更新权重
        break
    }
  }

  return { observations, vectorIndex, tagIndex }
}

// ===== 纯函数：语义召回 =====
export const recallBySemantic = (
  query: readonly number[],
  model: MemoryReadModel,
  limit: number
): readonly Observation[] => {
  const ids = model.vectorIndex.search(query, limit)
  return ids
    .map(id => model.observations.get(id))
    .filter((o): o is Observation => o !== undefined)
}
```

### 4.4 工作流域

```typescript
// packages/domain/src/workflows/types.ts

export type WorkflowState =
  | { readonly _tag: "Pending"; readonly dag: readonly TaskNode[] }
  | { readonly _tag: "Running"; readonly dag: readonly TaskNode[]; readonly executing: readonly string[] }
  | { readonly _tag: "Paused"; readonly dag: readonly TaskNode[]; readonly waitingFor: string }
  | { readonly _tag: "Completed"; readonly dag: readonly TaskNode[]; readonly results: ReadonlyMap<string, TaskResult> }
  | { readonly _tag: "Failed"; readonly dag: readonly TaskNode[]; readonly failedTask: string; readonly error: string }

export type WorkflowEvent =
  | { readonly _tag: "TaskStarted"; readonly taskId: string }
  | { readonly _tag: "TaskCompleted"; readonly taskId: string; readonly result: TaskResult }
  | { readonly _tag: "TaskFailed"; readonly taskId: string; readonly error: string }
  | { readonly _tag: "ApprovalRequired"; readonly taskId: string }
  | { readonly _tag: "ApprovalGranted"; readonly taskId: string }
  | { readonly _tag: "WorkflowCancelled" }

// 纯函数：拓扑排序
export const topologicalSort = (nodes: readonly TaskNode[]): TaskNode[] | CycleError => {
  // 纯函数：Kahn 算法
}

// 纯函数：获取可执行任务（依赖已完成的）
export const getExecutableTasks = (state: WorkflowState): readonly TaskNode[] => {
  if (state._tag !== "Running") return []
  
  return state.dag.filter(node => 
    node.dependencies.every(dep => 
      state.dag.find(n => n.id === dep)?.status === "completed"
    ) && node.status === "pending"
  )
}
```

### 4.5 权限域

```typescript
// packages/domain/src/permissions/types.ts

export type Decision =
  | { readonly _tag: "Allow" }
  | { readonly _tag: "Deny"; readonly reason: string }
  | { readonly _tag: "Ask"; readonly reason: string }

export type PermissionRule =
  | { readonly _tag: "AllowRule"; readonly pattern: string; readonly tool: string }
  | { readonly _tag: "DenyRule"; readonly pattern: string; readonly tool: string; readonly reason: string }
  | { readonly _tag: "AskRule"; readonly pattern: string; readonly tool: string; readonly reason: string }

// 纯函数：权限判定
export const evaluate = (
  rules: readonly PermissionRule[],
  tool: string,
  path: string
): Decision => {
  // 按优先级匹配规则
  for (const rule of rules) {
    if (rule.tool !== tool && rule.tool !== "*") continue
    if (!matchPattern(rule.pattern, path)) continue
    
    switch (rule._tag) {
      case "AllowRule": return { _tag: "Allow" }
      case "DenyRule": return { _tag: "Deny", reason: rule.reason }
      case "AskRule": return { _tag: "Ask", reason: rule.reason }
    }
  }
  
  // 默认拒绝
  return { _tag: "Deny", reason: "No matching rule" }
}
```

---

## 五、Effect 层：端口与服务

### 5.1 Service 定义（Effect Tags）

```typescript
// packages/contracts/src/services/llm.ts

import { Effect, Context, Stream } from "effect"
import type { Message, LLMResult, RetryableError } from "@butler/domain"

// ===== LLM Service Tag =====
export class LLMService extends Context.Tag("LLMService")<
  LLMService,
  {
    // 非流式调用
    readonly complete: (
      messages: readonly Message[],
      options?: LLMOptions
    ) => Effect.Effect<LLMResult, RetryableError, never>
    
    // 流式调用
    readonly stream: (
      messages: readonly Message[],
      options?: LLMOptions
    ) => Stream.Stream<StreamChunk, RetryableError, never>
    
    // 嵌入生成
    readonly embed: (
      text: string
    ) => Effect.Effect<readonly number[], EmbedError, never>
  }
>() {}

export interface LLMOptions {
  readonly model?: string
  readonly temperature?: number
  readonly maxTokens?: number
  readonly tools?: readonly ToolSchema[]
}
```

```typescript
// packages/contracts/src/services/database.ts

import { Effect, Context } from "effect"

export class DatabaseService extends Context.Tag("DatabaseService")<
  DatabaseService,
  {
    readonly query: <T>(sql: string, params?: readonly unknown[]) => 
      Effect.Effect<readonly T[], DatabaseError, never>
    
    readonly execute: (sql: string, params?: readonly unknown[]) => 
      Effect.Effect<{ affectedRows: number }, DatabaseError, never>
    
    readonly transaction: <A, E>(
      effect: Effect.Effect<A, E, DatabaseService>
    ) => Effect.Effect<A, E | DatabaseError, DatabaseService>
  }
>() {}
```

```typescript
// packages/contracts/src/services/eventstore.ts

import { Effect, Context, Stream } from "effect"
import type { DomainEvent } from "@butler/domain"

export class EventStore extends Context.Tag("EventStore")<
  EventStore,
  {
    // 追加事件
    readonly append: (
      aggregateId: string,
      event: DomainEvent,
      expectedVersion?: number
    ) => Effect.Effect<void, EventStoreError, never>
    
    // 读取事件流
    readonly read: (
      aggregateId: string,
      fromVersion?: number
    ) => Effect.Effect<readonly DomainEvent[], EventStoreError, never>
    
    // 订阅事件流（实时）
    readonly subscribe: (
      aggregateId: string
    ) => Stream.Stream<DomainEvent, EventStoreError, never>
    
    // 全局订阅（用于投影）
    readonly subscribeAll: (
      fromPosition?: number
    ) => Stream.Stream<{ aggregateId: string; event: DomainEvent; position: number }, EventStoreError, never>
  }
>() {}
```

### 5.2 默认 Layer 组合

```typescript
// packages/contracts/src/layers/production.ts

import { Layer } from "effect"
import { LLMService } from "../services/llm"
import { DatabaseService } from "../services/database"
import { EventStore } from "../services/eventstore"
// ... import 所有实现

// 生产环境 Layer 组合
export const ProductionLayers = Layer.mergeAll(
  LLMLive,           // OpenAI/Anthropic/MiniMax
  DatabaseLive,      // PostgreSQL + Drizzle
  EventStoreLive,    // PostgreSQL event store
  VectorLive,        // pgvector
  CacheLive,         // LRU + Redis (optional)
  ObservabilityLive, // OpenTelemetry
  WeChatLive,        // iLink 适配器
).pipe(
  Layer.provide(/* 基础配置 */)
)
```

```typescript
// packages/contracts/src/layers/test.ts

// 测试环境 Layer（全内存、零外部依赖）
export const TestLayers = Layer.mergeAll(
  LLMTestLive,           // Mock LLM 响应
  DatabaseTestLive,      // 内存数据库
  EventStoreTestLive,    // 内存事件存储
  VectorTestLive,        // 内存向量索引
  CacheTestLive,         // 内存缓存
  ObservabilityTestLive, // No-op 可观测性
  WeChatTestLive,        // Mock 微信
)
```

---

## 六、应用层：用例编排

### 6.1 Agent Loop 执行（核心用例）

```typescript
// packages/application/src/conversation/run-loop.ts

import { Effect, pipe } from "effect"
import type { LoopState, LoopEvent, LoopResult, LoopError } from "@butler/domain"
import { transition } from "@butler/domain"
import { LLMService } from "@butler/contracts"
import { prepareContext } from "./prepare-context"
import { callLLM } from "./call-llm"
import { executeTools } from "./execute-tools"

const MAX_TURNS = 50
const MAX_RETRIES = 3

/**
 * Agent Loop 主循环。
 * 函数式核心（transition）是纯函数；
 * 副作用（LLM调用、工具执行）在 Effect 中。
 */
export const runLoop = (
  userMessage: string,
  sessionId: string
): Effect.Effect<LoopResult, LoopError, LLMService | ToolService | MemoryService | ContextService> =>
  Effect.gen(function* (_) {
    // 初始状态
    let state: LoopState = { _tag: "Idle" }
    let event: LoopEvent = { _tag: "UserMessage", content: userMessage, sessionId }

    // 主循环
    while (state._tag !== "Completed" && state._tag !== "Failed" && state._tag !== "Interrupted") {
      // 1. 纯函数：状态转换（无副作用）
      state = transition(state, event)

      // 2. 根据新状态执行副作用
      event = yield* _(executeSideEffect(state))
      
      // 3. 安全检查
      if (state._tag === "Preparing" && state.turn > MAX_TURNS) {
        state = { _tag: "Failed", error: { _tag: "MaxRetriesExceeded", attempts: state.turn, lastError: "Max turns" } }
        break
      }
    }

    // 返回结果
    if (state._tag === "Completed") {
      return state.result
    }
    if (state._tag === "Failed") {
      return yield* _(Effect.fail(state.error))
    }
    return yield* _(Effect.fail({ _tag: "Interrupted", reason: state.reason }))
  })

// 根据状态执行对应的副作用
const executeSideEffect = (
  state: LoopState
): Effect.Effect<LoopEvent, never, LLMService | ToolService | MemoryService | ContextService> =>
  Effect.gen(function* (_) {
    switch (state._tag) {
      case "Preparing": {
        // 副作用：准备上下文（记忆召回、压缩）
        const messages = yield* _(prepareContext(state.input))
        return { _tag: "ContextReady", messages } satisfies LoopEvent
      }

      case "CallingLLM": {
        // 副作用：调用 LLM
        const response = yield* _(callLLM(state.messages))
        return {
          _tag: "LLMResponse",
          response,
          needsTools: response.toolCalls !== undefined && response.toolCalls.length > 0,
        } satisfies LoopEvent
      }

      case "ExecutingTools": {
        // 副作用：执行工具（并行）
        const results = yield* _(executeTools(state.pendingCalls))
        return { _tag: "ToolResults", results } satisfies LoopEvent
      }

      case "Compressing": {
        // 副作用：压缩上下文
        const compressed = yield* _(compressContext(state.messages, state.reason))
        return { _tag: "ContextReady", messages: compressed } satisfies LoopEvent
      }

      case "Retrying": {
        // 副作用：重试 LLM 调用
        if (state.attempt > MAX_RETRIES) {
          return { _tag: "Fail", error: { _tag: "MaxRetriesExceeded", attempts: state.attempt, lastError: state.error._tag } } satisfies LoopEvent
        }
        const response = yield* _(callLLM([])) // 重试
        return { _tag: "LLMResponse", response, needsTools: false } satisfies LoopEvent
      }

      default:
        // 终态：不需要事件
        return { _tag: "Complete", response: "" } satisfies LoopEvent
    }
  })
```

### 6.2 上下文准备

```typescript
// packages/application/src/conversation/prepare-context.ts

import { Effect, pipe } from "effect"
import type { Message, UserInput } from "@butler/domain"
import { MemoryService, ContextService } from "@butler/contracts"

/**
 * 准备上下文：记忆召回 + 压缩 + 卫生处理
 * 使用 pipe 组合多个纯函数和 Effect
 */
export const prepareContext = (
  input: UserInput
): Effect.Effect<readonly Message[], never, MemoryService | ContextService> =>
  Effect.gen(function* (_) {
    // 1. 召回相关记忆（副作用：向量搜索）
    const memories = yield* _(
      MemoryService.recall({ _tag: "RecallBySemantic", query: input.text, limit: 10 })
    )

    // 2. 构建初始消息列表（纯函数）
    const messages = buildMessages(input, memories)

    // 3. 估算 token（纯函数）
    const estimated = estimateTokens(messages)

    // 4. 如果超限，压缩（副作用：LLM 摘要）
    const finalMessages = estimated > TOKEN_LIMIT
      ? yield* _(compressMessages(messages, estimated))
      : messages

    // 5. 卫生处理（纯函数）
    return sanitizeMessages(finalMessages)
  })

// 纯函数：构建消息列表
const buildMessages = (
  input: UserInput,
  memories: readonly Memory[]
): readonly Message[] => [
  { _tag: "System", content: SYSTEM_PROMPT },
  ...memories.map(m => ({ _tag: "System" as const, content: formatMemory(m) })),
  { _tag: "User", content: input.text },
]
```

### 6.3 LLM 调用（带重试 + failover）

```typescript
// packages/application/src/conversation/call-llm.ts

import { Effect, Schedule, pipe } from "effect"
import type { Message, LLMResult, RetryableError } from "@butler/domain"
import { LLMService } from "@butler/contracts"

const PROVIDERS = ["anthropic", "openai", "minimax"] as const

/**
 * LLM 调用：带重试和 Provider failover
 * 使用 Effect 的 Schedule 组合器
 */
export const callLLM = (
  messages: readonly Message[]
): Effect.Effect<LLMResult, RetryableError, LLMService> =>
  Effect.gen(function* (_) {
    const llm = yield* _(LLMService)

    // 尝试每个 Provider
    for (const provider of PROVIDERS) {
      try {
        const result = yield* _(
          llm.complete(messages, { model: provider })
            .pipe(
              // 重试策略：空内容重试 2 次
              Effect.retry(
                Schedule.exponentialBackoff("1 second").pipe(
                  Schedule.recurs(2),
                  Schedule.whileInput((e): e is RetryableError =>
                    e._tag === "EmptyResponse" || e._tag === "RateLimited"
                  )
                )
              ),
              // 超时控制
              Effect.timeout("30 seconds")
            )
        )
        return result
      } catch (error) {
        // 该 Provider 失败，尝试下一个
        continue
      }
    }

    // 所有 Provider 都失败
    return yield* _(Effect.fail({ _tag: "AllProvidersFailed", providers: [...PROVIDERS] }))
  })
```

### 6.4 工具执行（并行 + Guardrails）

```typescript
// packages/application/src/conversation/execute-tools.ts

import { Effect, Fiber, Semaphore } from "effect"
import type { ToolCall, ToolResult, ToolError } from "@butler/domain"
import { ToolService, PermissionService } from "@butler/contracts"

const MAX_CONCURRENCY = 5

/**
 * 并行执行工具调用
 * 使用 Fiber + Semaphore 控制并发
 */
export const executeTools = (
  calls: readonly ToolCall[]
): Effect.Effect<readonly ToolResult[], ToolError, ToolService | PermissionService> =>
  Effect.gen(function* (_) {
    const semaphore = yield* _(Semaphore.make(MAX_CONCURRENCY))
    const toolService = yield* _(ToolService)
    const permissionService = yield* _(PermissionService)

    // 为每个工具调用创建 Fiber
    const fibers = yield* _(
      Effect.forEach(calls, (call) =>
        Effect.gen(function* (_) {
          // 1. 权限检查（纯函数 + 副作用）
          const decision = yield* _(permissionService.check(call))
          if (decision._tag === "Deny") {
            return { _tag: "Failure", error: { _tag: "PermissionDenied", resource: call.name, rule: decision.reason } } satisfies ToolResult
          }

          // 2. 信号量控制并发
          yield* _(semaphore.acquire)
          return yield* _(
            Effect.gen(function* (_) {
              // 3. 执行工具（副作用）
              const result = yield* _(toolService.execute(call))
              return result
            }).pipe(
              Effect.ensuring(semaphore.release),
              // 4. 超时控制
              Effect.timeout("30 seconds"),
              // 5. 错误恢复：单个工具失败不影响其他
              Effect.catchAll((error) =>
                Effect.succeed({ _tag: "Failure", error } satisfies ToolResult)
              )
            )
          )
        }).pipe(Effect.fork) // 创建 Fiber
      )
    )

    // 等待所有 Fiber 完成
    const results = yield* _(
      Effect.forEach(fibers, (fiber) => fiber.join)
    )

    return results
  })
```

---

## 七、基础设施层：命令式外壳

### 7.1 LLM 客户端实现

```typescript
// packages/infrastructure/src/llm/client.ts

import { Effect, Layer } from "effect"
import { LLMService } from "@butler/contracts"
import type { Message, LLMResult, RetryableError } from "@butler/domain"
import Anthropic from "@anthropic-ai/sdk"
import OpenAI from "openai"

// LLM 客户端实现（命令式外壳）
const makeLLMLive = Effect.gen(function* (_) {
  // 初始化各 Provider 客户端
  const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY })
  const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY })

  return {
    complete: (messages, options) =>
      Effect.gen(function* (_) {
        // 选择 Provider
        const provider = options?.model ?? "anthropic"
        
        if (provider === "anthropic") {
          // 副作用：HTTP 调用
          const response = yield* _(
            Effect.tryPromise({
              try: () => anthropic.messages.create({
                model: options?.model ?? "claude-sonnet-4-20250514",
                messages: messages.map(toAnthropicFormat),
                max_tokens: options?.maxTokens ?? 4096,
              }),
              catch: (e) => ({ _tag: "ProviderError", reason: String(e) }) satisfies RetryableError
            })
          )
          
          return fromAnthropicResponse(response)
        }
        
        // ... 其他 Provider
      }),

    stream: (messages, options) =>
      // 流式实现...
      Effect.succeed(undefined as any),

    embed: (text) =>
      // 嵌入生成...
      Effect.succeed([]),
  }
})

export const LLMLive = Layer.effect(LLMService, makeLLMLive)
```

### 7.2 数据库 Schema（Drizzle）

```typescript
// packages/infrastructure/src/database/schema.ts

import { pgTable, uuid, text, jsonb, timestamp, integer, vector, index } from "drizzle-orm/pg-core"

// 会话表
export const sessions = pgTable("sessions", {
  id: uuid("id").defaultRandom().primaryKey(),
  sessionKey: text("session_key").notNull().unique(),
  projectId: uuid("project_id"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
  lastActivity: timestamp("last_activity").defaultNow().notNull(),
  status: text("status").notNull().default("active"),
})

// 消息表（事件溯源）
export const messages = pgTable("messages", {
  id: uuid("id").defaultRandom().primaryKey(),
  sessionId: uuid("session_id").references(() => sessions.id).notNull(),
  role: text("role").notNull(), // system | user | assistant | tool | compacted
  content: text("content").notNull(),
  toolCalls: jsonb("tool_calls"),
  metadata: jsonb("metadata"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
}, (t) => ({
  sessionIdx: index("messages_session_idx").on(t.sessionId),
}))

// 事件存储表
export const events = pgTable("events", {
  id: uuid("id").defaultRandom().primaryKey(),
  aggregateId: text("aggregate_id").notNull(),
  aggregateType: text("aggregate_type").notNull(),
  eventType: text("event_type").notNull(),
  payload: jsonb("payload").notNull(),
  version: integer("version").notNull(),
  createdAt: timestamp("created_at").defaultNow().notNull(),
}, (t) => ({
  aggregateIdx: index("events_aggregate_idx").on(t.aggregateId, t.version),
  typeIdx: index("events_type_idx").on(t.aggregateType),
}))

// 观察表（记忆系统）
export const observations = pgTable("observations", {
  id: uuid("id").defaultRandom().primaryKey(),
  content: text("content").notNull(),
  embedding: vector("embedding", { dimensions: 384 }),
  metadata: jsonb("metadata"),
  tags: jsonb("tags"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
  expiredAt: timestamp("expired_at"),
}, (t) => ({
  embeddingIdx: index("observations_embedding_idx").using("hnsw", t.embedding),
}))

// 工具审计表
export const toolAudits = pgTable("tool_audits", {
  id: uuid("id").defaultRandom().primaryKey(),
  sessionId: uuid("session_id").references(() => sessions.id).notNull(),
  toolName: text("tool_name").notNull(),
  toolInput: jsonb("tool_input"),
  toolResult: jsonb("tool_result"),
  durationMs: integer("duration_ms"),
  success: boolean("success").notNull(),
  createdAt: timestamp("created_at").defaultNow().notNull(),
})
```

---

## 八、事件溯源 + CQRS

### 8.1 事件存储实现

```typescript
// packages/infrastructure/src/eventstore/postgres-store.ts

import { Effect, Layer, Stream } from "effect"
import { EventStore } from "@butler/contracts"
import type { DomainEvent } from "@butler/domain"
import { DatabaseService } from "@butler/contracts"

const makeEventStore = Effect.gen(function* (_) {
  const db = yield* _(DatabaseService)

  return {
    append: (aggregateId, event, expectedVersion) =>
      Effect.gen(function* (_) {
        // 乐观并发控制
        const version = expectedVersion !== undefined
          ? yield* _(getCurrentVersion(db, aggregateId))
          : 0

        if (expectedVersion !== undefined && version !== expectedVersion) {
          return yield* _(Effect.fail({
            _tag: "ConcurrentModification",
            aggregateId,
            expected: expectedVersion,
            actual: version,
          }))
        }

        // 追加事件
        yield* _(db.execute(
          `INSERT INTO events (aggregate_id, aggregate_type, event_type, payload, version)
           VALUES ($1, $2, $3, $4, $5)`,
          [aggregateId, event._tag.split("_")[0], event._tag, JSON.stringify(event), version + 1]
        ))
      }),

    read: (aggregateId, fromVersion) =>
      Effect.gen(function* (_) {
        const rows = yield* _(db.query<{ payload: DomainEvent; version: number }>(
          `SELECT payload, version FROM events WHERE aggregate_id = $1 AND version >= $2 ORDER BY version`,
          [aggregateId, fromVersion ?? 0]
        ))
        return rows.map(r => r.payload)
      }),

    subscribe: (aggregateId) =>
      Stream.fromEffect(db.query(
        `SELECT payload FROM events WHERE aggregate_id = $1 ORDER BY version`,
        [aggregateId]
      )).pipe(
        Stream.flatMap(rows => Stream.fromIterable(rows.map(r => r.payload)))
      ),

    subscribeAll: (fromPosition) =>
      Stream.repeatEffectWithSchedule(
        db.query<{ aggregate_id: string; payload: DomainEvent; position: number }>(
          `SELECT aggregate_id, payload, id as position FROM events WHERE id > $1 ORDER BY id`,
          [fromPosition ?? 0]
        ),
        Schedule.spaced("100 millis")
      ).pipe(
        Stream.flatMap(rows => Stream.fromIterable(rows))
      ),
  }
})

export const EventStoreLive = Layer.effect(EventStore, makeEventStore)
```

### 8.2 CQRS 读模型投影

```typescript
// packages/infrastructure/src/eventstore/projections/

import { Effect, Layer, Stream } from "effect"
import { EventStore, DatabaseService } from "@butler/contracts"
import type { MemoryEvent, MemoryReadModel } from "@butler/domain"

// 记忆读模型投影器
const memoryProjection = Effect.gen(function* (_) {
  const eventStore = yield* _(EventStore)
  const db = yield* _(DatabaseService)

  // 订阅所有记忆事件
  yield* _(
    eventStore.subscribeAll().pipe(
      Stream.filter(({ event }) => isMemoryEvent(event)),
      Stream.runForEach(({ aggregateId, event }) =>
        Effect.gen(function* (_) {
          switch (event._tag) {
            case "ObservationStored":
              // 更新读模型
              yield* _(db.execute(
                `INSERT INTO observations (id, content, tags, metadata, created_at)
                 VALUES ($1, $2, $3, $4, $5)
                 ON CONFLICT (id) DO NOTHING`,
                [aggregateId, event.observation.content, event.observation.tags,
                 JSON.stringify(event.observation.metadata), event.timestamp]
              ))
              break
            case "ObservationExpired":
              yield* _(db.execute(
                `UPDATE observations SET expired_at = NOW() WHERE id = $1`,
                [aggregateId]
              ))
              break
          }
        })
      ),
      Stream.runDrain
    )
  )
})

export const ProjectionWorkerLive = Layer.effectDiscard(memoryProjection)
```

---

## 九、网关层（命令式外壳入口）

### 9.1 HTTP 网关

```typescript
// apps/gateway/src/index.ts

import { Hono } from "hono"
import { Effect, Runtime } from "effect"
import { runLoop } from "@butler/application"
import { ProductionLayers } from "@butler/contracts"

const app = new Hono()

// 创建 Effect Runtime（注入所有生产环境依赖）
const runtime = Runtime.make({
  layers: [ProductionLayers],
})

// POST /chat — 对话接口
app.post("/chat", async (c) => {
  const { message, sessionId } = await c.req.json()

  // 运行 Agent Loop（Effect → Promise）
  const result = await Runtime.runPromise(runtime)(
    runLoop(message, sessionId).pipe(
      Effect.timeout("120 seconds"),
      Effect.catchAll((error) =>
        Effect.succeed({ error: error._tag })
      )
    )
  )

  return c.json(result)
})

// 启动服务
export default {
  port: 3000,
  fetch: app.fetch,
}
```

### 9.2 微信网关

```typescript
// apps/gateway/src/wechat/handler.ts

import { Effect, Runtime } from "effect"
import { WeChatService } from "@butler/contracts"
import { runLoop } from "@butler/application"

// 微信消息处理器
export const handleWeChatMessage = (
  message: WeChatInbound,
  runtime: Runtime.Runtime<any>
) =>
  Runtime.runPromise(runtime)(
    Effect.gen(function* (_) {
      const wechat = yield* _(WeChatService)

      // 1. 入站消息校验
      const validated = yield* _(wechat.validateInbound(message))

      // 2. 运行 Agent Loop
      const result = yield* _(
        runLoop(validated.content, validated.sessionKey)
      )

      // 3. 出站消息发送
      yield* _(wechat.sendReply({
        toUser: validated.fromUser,
        content: result.response,
      }))
    }).pipe(
      Effect.catchAll((error) =>
        Effect.gen(function* (_) {
          const wechat = yield* _(WeChatService)
          yield* _(wechat.sendReply({
            toUser: message.fromUser,
            content: `抱歉，处理消息时出错：${error._tag}`,
          }))
        })
      )
    )
  )
```

---

## 十、配置管理

### 10.1 统一配置 Schema

```typescript
// packages/contracts/src/config.ts

import { Schema } from "effect"
import { Config, ConfigSecret } from "effect"

// 用 Effect Schema 定义所有配置（替代 200+ 环境变量）
export const AppConfig = Schema.Struct({
  // LLM 配置
  llm: Schema.Struct({
    defaultProvider: Schema.Literal("anthropic", "openai", "minimax").pipe(
      Schema.withDefaultsDefault("anthropic")
    ),
    models: Schema.Record({ key: Schema.String, value: Schema.String }),
    maxRetries: Schema.Number.pipe(Schema.withDefaultsDefault(3)),
    timeout: Schema.Duration,
  }),

  // 数据库配置
  database: Schema.Struct({
    url: ConfigSecret,
    poolSize: Schema.Number.pipe(Schema.withDefaultsDefault(10)),
  }),

  // 微信配置
  wechat: Schema.Struct({
    token: ConfigSecret,
    accountId: Schema.String,
    baseUrl: Schema.String.pipe(Schema.withDefaultsDefault("https://ilinkai.weixin.qq.com")),
    allowedUsers: Schema.Array(Schema.String),
  }),

  // 记忆配置
  memory: Schema.Struct({
    embeddingModel: Schema.String.pipe(Schema.withDefaultsDefault("BAAI/bge-small-en")),
    vectorDimensions: Schema.Number.pipe(Schema.withDefaultsDefault(384)),
    recallLimit: Schema.Number.pipe(Schema.withDefaultsDefault(10)),
  }),

  // 工具配置
  tools: Schema.Struct({
    enabledTools: Schema.Array(Schema.String),
    maxConcurrency: Schema.Number.pipe(Schema.withDefaultsDefault(5)),
    enableTerminal: Schema.Boolean.pipe(Schema.withDefaultsDefault(false)),
  }),
})

export type AppConfig = Schema.Schema.Type<typeof AppConfig>

// 从环境变量加载配置
export const loadConfig: Effect.Effect<AppConfig, ConfigError> = Effect.gen(function* (_) {
  // Effect Config 原生支持环境变量
  return yield* _(Config.all({
    llm: Config.all({
      defaultProvider: Config.string("LLM_PROVIDER").pipe(Config.withDefault("anthropic")),
      // ...
    }),
    // ...
  }))
})
```

### 10.2 配置优先级

```
1. 环境变量（部署覆盖）
2. ~/.butler/config.yaml（用户配置）
3. 代码默认值（Schema defaults）
```

**不再有 200+ 散落的 `BUTLER_*` 变量**，所有配置通过 Schema 统一管理、类型安全、有默认值。

---

## 十一、测试策略

### 11.1 三层测试

```
┌───────────────────────────────────────────────────┐
│  Level 1: 纯函数测试（domain/）                     │
│  • 零 mock、零依赖                                  │
│  • 输入→输出，确定性                                 │
│  • 覆盖率目标：100%                                  │
│  • 示例：状态转换、权限判定、拓扑排序                  │
│  • 速度：1000 个测试 < 1 秒                          │
├───────────────────────────────────────────────────┤
│  Level 2: 用例测试（application/）                  │
│  • Mock Layer 替代真实依赖                            │
│  • 测试业务编排逻辑                                   │
│  • 覆盖率目标：90%                                    │
│  • 示例：Agent Loop 流程、工具执行顺序                │
│  • 速度：100 个测试 < 5 秒                            │
├───────────────────────────────────────────────────┤
│  Level 3: 集成测试（infrastructure/）                │
│  • 真实 PostgreSQL + HTTP                            │
│  • 测试适配器实现                                    │
│  • 覆盖率目标：70%                                    │
│  • 示例：数据库 CRUD、LLM API 调用、微信协议          │
│  • 速度：50 个测试 < 30 秒                            │
└───────────────────────────────────────────────────┘
```

### 11.2 纯函数测试示例

```typescript
// packages/domain/tests/conversation/transition.test.ts
// 零 mock，零依赖，纯输入输出

import { describe, test, expect } from "bun:test"
import { transition } from "../../src/conversation/transition"

describe("Agent Loop 状态转换", () => {
  describe("Idle 状态", () => {
    test("UserMessage → Preparing", () => {
      const result = transition(
        { _tag: "Idle" },
        { _tag: "UserMessage", content: "hello", sessionId: "s1" }
      )
      expect(result._tag).toBe("Preparing")
    })

    test("忽略不相关事件", () => {
      const result = transition(
        { _tag: "Idle" },
        { _tag: "LLMResponse", response: {}, needsTools: false }
      )
      expect(result._tag).toBe("Idle") // 状态不变
    })
  })

  describe("ExecutingTools → CallingLLM", () => {
    test("ToolResults 触发新一轮 LLM 调用", () => {
      const result = transition(
        { _tag: "ExecutingTools", pendingCalls: [], turn: 1 },
        { _tag: "ToolResults", results: [{ _tag: "Success", content: "file content" }] }
      )
      expect(result._tag).toBe("CallingLLM")
      expect(result.turn).toBe(2) // 轮次递增
    })
  })

  describe("终态保护", () => {
    test("Completed 状态不接受任何事件", () => {
      const completed = { _tag: "Completed", result: { response: "done", turn: 1 } }
      
      // 任何事件都不能改变终态
      const events = [
        { _tag: "UserMessage", content: "more", sessionId: "s1" },
        { _tag: "Interrupt", reason: "test" },
      ] as const

      for (const event of events) {
        expect(transition(completed, event)).toBe(completed)
      }
    })
  })
})
```

### 11.3 用例测试示例（Mock Layer）

```typescript
// packages/application/tests/run-loop.test.ts

import { describe, test, expect, mock } from "bun:test"
import { Effect, Layer, TestContext } from "effect"
import { runLoop } from "../src/conversation/run-loop"
import { LLMService, ToolService, MemoryService } from "@butler/contracts"
import { TestLayers } from "@butler/contracts/layers/test"

describe("runLoop", () => {
  test("简单对话：用户消息 → LLM 响应 → 完成", async () => {
    // Mock LLM 返回固定响应
    const mockLLM = Layer.succeed(LLMService, {
      complete: () => Effect.succeed({
        content: "你好！我是管家。",
        toolCalls: undefined,
      }),
      stream: () => Effect.succeed(undefined as any),
      embed: () => Effect.succeed([]),
    })

    const result = await Effect.runPromise(
      runLoop("你好", "session-1").pipe(
        Effect.provide(TestLayers.pipe(Layer.provide(mockLLM)))
      )
    )

    expect(result.response).toBe("你好！我是管家。")
  })

  test("工具调用：用户消息 → LLM → 工具 → LLM → 完成", async () => {
    // 第一次 LLM 调用返回工具调用
    // 第二次 LLM 调用返回最终响应
    let callCount = 0
    const mockLLM = Layer.succeed(LLMService, {
      complete: () => Effect.gen(function* (_) {
        callCount++
        if (callCount === 1) {
          return { content: "", toolCalls: [{ name: "read_file", args: { path: "/tmp/test" } }] }
        }
        return { content: "文件内容是：hello world", toolCalls: undefined }
      }),
      // ...
    })

    const mockTool = Layer.succeed(ToolService, {
      execute: () => Effect.succeed({ _tag: "Success", content: "hello world" }),
    })

    const result = await Effect.runPromise(
      runLoop("读取文件", "session-1").pipe(
        Effect.provide(TestLayers.pipe(
          Layer.provide(mockLLM),
          Layer.provide(mockTool),
        ))
      )
    )

    expect(result.response).toContain("hello world")
    expect(callCount).toBe(2) // LLM 被调用两次
  })
})
```

---

## 十二、与 Python v4 的对比

| 维度 | Python v4 | TypeScript v5 |
|------|-----------|---------------|
| **文件数** | 1,490 | ~200（预估） |
| **代码行数** | ~197K | ~30K（预估） |
| **测试数** | 12,058 | ~500（预估） |
| **配置项** | 200+ 散落变量 | 1 个 Schema |
| **全局状态** | 9 个模块级单例 | 0（Layer DI） |
| **错误处理** | try/except 散布 | ADT + Effect |
| **并发模型** | threading + 锁 | Fiber |
| **测试隔离** | 需手动重置全局状态 | 天然隔离（Mock Layer） |
| **类型安全** | mypy strict（可选） | tsc strict（强制） |
| **初始内存** | 15MB（优化后） | <5MB（预估） |

---

## 十三、实施计划

### Phase 1：核心域 + POC（Week 1-4）

| 周 | 任务 | 产出 |
|----|------|------|
| 1 | 搭建 Monorepo + domain/ 对话域 | ADT + 纯函数 + 测试 |
| 2 | contracts/ + application/ 对话用例 | Effect Layer + Agent Loop |
| 3 | infrastructure/ LLM + DB | LLM 客户端 + Drizzle Schema |
| 4 | 集成测试 + POC 验证 | 端到端对话流程 |

### Phase 2：完整域（Week 5-8）

| 周 | 任务 | 产出 |
|----|------|------|
| 5 | 工具域 + 记忆域 | 工具注册 + 向量搜索 |
| 6 | 工作流域 + 权限域 | DAG 执行 + 权限判定 |
| 7 | 项目域 + 事件溯源 | CQRS + 读模型投影 |
| 8 | 集成测试 + 性能调优 | 全域测试通过 |

### Phase 3：网关 + 部署（Week 9-12）

| 周 | 任务 | 产出 |
|----|------|------|
| 9 | 微信网关 + HTTP 服务 | Hono + iLink 适配器 |
| 10 | CLI + Worker | 命令行 + 后台任务 |
| 11 | Docker + CI/CD | 容器化 + 自动部署 |
| 12 | 文档 + 性能优化 | 完整文档 + 基准测试 |

### Phase 4：迁移 + 收尾（Week 13-16）

| 周 | 任务 | 产出 |
|----|------|------|
| 13 | 数据迁移脚本 | ChromaDB → pgvector |
| 14 | 并行运行 + 校验 | 影子模式验证 |
| 15 | 流量切换 | 100% 切到新系统 |
| 16 | Python 退役 | 老代码归档 |

**总计**：16 周（4 个月），含完整测试和文档。

# Butler v5 — 完整设计方案（SSOT）

> **日期**：2026-07-30
> **定位**：Butler v5 函数式架构的**单一权威设计文档**（Single Source of Truth）
> **整合来源**：
> - [`butler-v5-functional-architecture-2026-07-30.md`](butler-v5-functional-architecture-2026-07-30.md) — 主架构
> - [`butler-v5-optimization-from-projects-2026-07-30.md`](butler-v5-optimization-from-projects-2026-07-30.md) — 18 条优化建议
> - [`functional-architecture-migration-plan-2026-07-30.md`](functional-architecture-migration-plan-2026-07-30.md) — 迁移主方案
> - [`strangler-fig-migration-guide-2026-07-30.md`](strangler-fig-migration-guide-2026-07-30.md) — 绞杀者模式
> - [`functional-migration-supplement-2026-07-30.md`](functional-migration-supplement-2026-07-30.md) — 数据迁移补充
>
> **本文档优先级最高**：与上述文档冲突时以本文为准。优化建议已直接融入对应章节，标注 `[OPT-N]` 引用来源。

---

## 目录

1. [执行摘要](#一执行摘要)
2. [背景与动机](#二背景与动机)
3. [设计原则与范式](#三设计原则与范式)
4. [技术选型](#四技术选型)
5. [架构总览](#五架构总览)
6. [领域模型设计](#六领域模型设计)
7. [端口与服务（Effect Tags）](#七端口与服务effect-tags)
8. [应用层：用例编排](#八应用层用例编排)
9. [基础设施层：命令式外壳](#九基础设施层命令式外壳)
10. [事件溯源 + CQRS](#十事件溯源--cqrs)
11. [网关层](#十一网关层)
12. [配置管理](#十二配置管理)
13. [测试策略](#十三测试策略)
14. [可观测性](#十四可观测性)
15. [迁移计划：绞杀者模式](#十五迁移计划绞杀者模式)
16. [实施路线图](#十六实施路线图)
17. [验证标准](#十七验证标准)
18. [不采纳设计](#十八不采纳设计)
19. [附录：18 条优化建议索引](#十九附录18-条优化建议索引)

---

## 一、执行摘要

Butler v5 是对现有 Python v4 的**函数式重写**，采用 **TypeScript + Effect-TS**，核心范式为 **函数式核心 + 命令式外壳（FC/IS）**。

**核心升级**（相对 v4）：
- **领域层零副作用**：所有业务逻辑为纯函数 + ADT，可单测零 mock
- **副作用显式化**：所有 I/O 包裹在 Effect 中，类型签名声明依赖
- **依赖注入**：Effect Layer 取代 9 个模块级单例
- **事件溯源**：状态变更通过事件流追溯，Hybrid Store 平衡性能与纯度 `[OPT-12]`
- **Spec 驱动开发**：`delegate_task` 接受 Spec 引用而非自由文本 `[OPT-3]`
- **Loop 可中断**：`interrupt/resume` 原语让任意工具可暂停 Loop 等外部输入 `[OPT-2]`
- **Channel 工作流**：多分支并行状态合并由 reducer 自动处理 `[OPT-1]`

**实施周期**：16 周（4 个月），分 4 个 Phase 渐进交付。

**与 v4 对比**：

| 维度 | Python v4 | TypeScript v5 |
|------|-----------|---------------|
| 文件数 | 1,490 | ~200 |
| 代码行数 | ~197K | ~30K |
| 测试数 | 12,058 | ~500 |
| 配置项 | 200+ 散落变量 | 1 个 Effect Schema |
| 全局状态 | 9 个模块级单例 | 0（Layer DI） |
| 错误处理 | try/except 散布 | ADT + Effect |
| 并发模型 | threading + 锁 | Fiber |
| 初始内存 | 15MB（优化后） | <5MB |

---

## 二、背景与动机

### 2.1 v4 的根本问题

| 根本问题 | 表现 | 根因 |
|----------|------|------|
| 副作用与逻辑混杂 | 12,058 个测试需要大量 mock | 没有 FC/IS 分离 |
| 状态不可追踪 | 200+ 全局变量、9 个模块级单例 | 没有事件溯源 |
| 错误处理分散 | try/except 散布在 1,490 个文件 | 没有统一错误 ADT |
| 模块边界模糊 | core/ 299 文件、core→ops 22 处违规导入 | 没有 Layer 依赖注入 |
| 并发控制脆弱 | 线程锁、全局可变状态 | 没有 Fiber 模型 |
| 配置爆炸 | 200+ BUTLER_* 环境变量 | 没有配置 Schema |

### 2.2 v5 的核心理念

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   纯函数可测试      ←→     副作用可控                              │
│                                                                 │
│   ADT 让非法状态不可表示      Effect 让副作用可组合                │
│                                                                 │
│   Event Sourcing 让状态可追溯    Layer 让依赖可替换                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、设计原则与范式

### 3.1 六条设计原则

1. **非法状态不可表示** — 用 ADT 建模，编译期消除非法状态
2. **纯函数优先** — 业务逻辑零副作用，输入相同→输出相同
3. **副作用显式化** — 所有 I/O 包裹在 Effect，类型签名声明依赖
4. **组合优于继承** — 用 pipe/flatMap 组合，不用类继承
5. **错误是值** — 用 Either/Result 表示错误，不用 throw
6. **不可变优先** — 数据用 readonly，状态变更通过事件

### 3.2 FC/IS 边界划分

```
┌──────────────────────────────────────────────────────────────────┐
│  Functional Core（domain/）                                       │
│  ─────────────────────────────────────                            │
│  • ADT 类型定义（LoopState, ToolCall, Observation...）           │
│  • 纯函数（transition, policy, chooseStrategy...）               │
│  • 零依赖，零副作用，可单测零 mock                                │
│  • 不可变数据（readonly），状态变更通过事件                       │
└──────────────────────────────────────────────────────────────────┘
                          ↑ 依赖方向单向
┌──────────────────────────────────────────────────────────────────┐
│  Imperative Shell（application/ + infrastructure/ + apps/）       │
│  ─────────────────────────────────────────────────────────────    │
│  • Effect.gen 组合业务流程                                        │
│  • Layer 依赖注入（DB, LLM, MCP, WeChat...）                     │
│  • I/O 副作用（数据库读写、HTTP、文件、微信 API）                │
│  • Fiber 并发、Schedule 重试、Stream 事件流                      │
└──────────────────────────────────────────────────────────────────┘
```

**判定规则**：能写成纯函数的就放 `domain/`；必须做 I/O 的放 `application/`（编排）或 `infrastructure/`（实现）。

### 3.3 ADT 建模约定

```typescript
// 所有 union 类型用 _tag 区分
export type X =
  | { readonly _tag: "CaseA"; readonly field: string }
  | { readonly _tag: "CaseB"; readonly count: number }

// 所有字段 readonly
// 禁止 optional + null，用 Option<T> 或可辨识 union
```

### 3.4 错误是值

```typescript
// 禁止 throw
// 错误用 ADT 表示
export type LoopError =
  | { readonly _tag: "LLMUnavailable"; readonly provider: string }
  | { readonly _tag: "ContextOverflow"; readonly tokens: number }
  | { readonly _tag: "ToolFailed"; readonly toolId: string; readonly cause: string }

// Effect 中用 Effect.fail
yield* Effect.fail({ _tag: "LLMUnavailable", provider: "openai" })
```

---

## 四、技术选型

### 4.1 核心技术栈

| 类别 | 选择 | 版本 | 选择理由 |
|------|------|------|----------|
| 语言 | TypeScript | 5.5+ | ADT、条件类型、模板字面量足够表达 |
| 运行时 | Bun | 1.1+ | 原生 TS 执行、内置测试/打包、比 Node 快 3-4x |
| 函数式框架 | Effect-TS | 3.x | Layer（DI）、Fiber（并发）、Schedule（重试）、Stream |
| 数据库 | PostgreSQL | 16+ | 关系型 + pgvector 向量搜索，统一存储 |
| ORM | Drizzle ORM | 0.33+ | 类型安全 SQL，零运行时开销 |
| HTTP 框架 | Hono | 4.x | 轻量、类型安全、Bun 原生支持 |
| Schema 校验 | Effect Schema | 0.60+ | 编译期+运行时双重校验，与 Effect 深度集成 |
| 包管理 | pnpm | 9+ | workspace、硬链接节省磁盘 |
| Monorepo | Turborepo | 2+ | 增量构建、远程缓存、任务编排 |
| 测试 | Bun test | — | 原生集成、零配置、极快 |
| 容器 | Docker + Compose | — | 开发+部署统一环境 |

### 4.2 为什么选 Effect-TS 而非 fp-ts

| 维度 | fp-ts | Effect-TS |
|------|-------|-----------|
| 依赖注入 | ❌ 手动 Reader Monad | ✅ Layer 原生 |
| 并发 | ❌ 手动 Promise 管理 | ✅ Fiber 模型 |
| 重试 | ❌ 自己实现 | ✅ Schedule 组合器 |
| 资源管理 | ❌ 手动 bracket | ✅ acquireRelease/Scope |
| 可观测性 | ❌ 无 | ✅ 内置 tracing/metrics |
| 流处理 | ❌ 需 RxJS | ✅ Stream 原生 |

**结论**：Effect-TS 是 fp-ts 的超集，选择 Effect-TS 意味着不需要 fp-ts。

### 4.3 为什么不用 Scala + ZIO

- 单语言团队成本（前端、网关、CLI 都需 TS）
- Bun 性能 + 原生 TS 执行已足够
- Effect-TS 与 ZIO 理念相通，但生态更适合 Web 场景

---

## 五、架构总览

### 5.1 Monorepo 结构

```
butler-v5/
├── apps/                           # 可执行应用（命令式外壳入口）
│   ├── gateway/                    # 微信网关 + HTTP 服务
│   ├── cli/                        # 命令行界面
│   └── worker/                     # 后台 Worker（Outbox/eval/定时任务）
│
├── packages/                       # 可复用包
│   ├── domain/                     # 📦 领域核心（纯函数，零依赖）
│   ├── application/                 # 📦 应用层（Effect 组合，编排）
│   ├── infrastructure/            # 📦 基础设施（命令式外壳实现）
│   ├── contracts/                # 📦 端口接口（Effect Tags）
│   └── shared/                   # 📦 共享工具
│
├── turbo.json                    # Turborepo 配置
├── pnpm-workspace.yaml
├── package.json
├── tsconfig.base.json            # 共享 TS 配置
└── docker-compose.yml            # 开发环境
```

### 5.2 包依赖规则

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

### 5.3 包职责详表

| 包 | 职责 | 依赖 | 测试策略 |
|----|------|------|---------|
| `domain/` | ADT + 纯函数 | 零 | 零 mock 单测，代数定律 |
| `contracts/` | Effect Tag 接口 | effect, domain | 接口稳定性测试 |
| `application/` | 用例编排（Effect.gen） | domain, contracts | Mock Layer 测试 |
| `infrastructure/` | I/O 实现 | contracts | 集成测试（真实 DB/HTTP） |
| `shared/` | 通用工具（crypto/time） | 零 | 普通单测 |
| `apps/` | 入口组装 | application, infrastructure | 端到端测试 |

---

## 六、领域模型设计

`packages/domain/src/` 下的领域划分。每个域含 `types.ts`（ADT）+ 纯函数模块 + `index.ts`。

### 6.1 对话域（Conversation）

#### 6.1.1 LoopState 状态机 ADT

```typescript
// packages/domain/src/conversation/types.ts

export type LoopState =
  | { readonly _tag: "Idle" }
  | { readonly _tag: "Preparing"; readonly input: UserInput; readonly turn: number }
  | { readonly _tag: "CallingLLM"; readonly messages: readonly Message[]; readonly turn: number }
  | { readonly _tag: "ExecutingTools"; readonly pendingCalls: readonly ToolCall[]; readonly turn: number }
  | { readonly _tag: "Compressing"; readonly reason: CompressReason; readonly strategy: CompressStrategy; readonly messages: readonly Message[]; readonly preserveTail: number }
  | { readonly _tag: "Retrying"; readonly attempt: number; readonly error: RetryableError }
  | { readonly _tag: "Interrupted"; readonly reason: InterruptReason; readonly interruptId: string }
  | { readonly _tag: "Completed"; readonly result: LoopResult }
  | { readonly _tag: "Failed"; readonly error: LoopError }
```

> `[OPT-2]` 新增 `Interrupted` 状态支持 Loop 中断恢复。
> `[OPT-8]` `Compressing` 状态携带 `strategy` + `preserveTail`，支持双策略压缩。

#### 6.1.2 双策略压缩 ADT `[OPT-8]`

```typescript
export type CompressReason =
  | { readonly _tag: "BudgetOverflow"; readonly tokens: number; readonly limit: number }
  | { readonly _tag: "TurnLimit"; readonly turns: number; readonly limit: number }
  | { readonly _tag: "Manual" }

export type CompressStrategy = "truncate" | "summarize" | "hybrid"

// 纯函数：策略选择
export const chooseStrategy = (reason: CompressReason, budget: TokenBudget): CompressStrategy => {
  if (reason._tag === "BudgetOverflow" && reason.tokens > reason.limit * 1.2)
    return "truncate"  // 紧急溢出先救场
  if (budget.remaining > 4000) return "summarize"
  return "hybrid"
}
```

#### 6.1.3 AgentPersona 三元组 `[OPT-10]`

```typescript
// packages/domain/src/conversation/persona.ts
export type AgentPersona = {
  readonly role: string         // "代码审查员"
  readonly goal: string         // "保证代码质量"
  readonly backstory: string    // "你是资深工程师..."
  readonly tools: readonly string[]  // 允许的工具 id
  readonly canRefactor: boolean
  readonly canRemove: boolean
}

// 内置 persona
export const Personas = {
  build: { role: "开发执行员", goal: "完成编码任务", backstory: "...", canRefactor: true, canRemove: false } satisfies AgentPersona,
  plan: { role: "规划员", goal: "只读规划", backstory: "...", canRefactor: false, canRemove: false } satisfies AgentPersona,
  explore: { role: "代码库探索员", goal: "理解代码", backstory: "...", canRefactor: false, canRemove: false } satisfies AgentPersona,
} as const
```

#### 6.1.4 ContextGraph 有向图 `[OPT-16]`

```typescript
// packages/domain/src/conversation/context-graph.ts
export type ContextNode = {
  readonly id: string
  readonly content: string
  readonly provenance: Provenance
  readonly createdAt: number
}

export type Provenance =
  | { readonly _tag: "User" }
  | { readonly _tag: "Tool"; readonly toolId: string; readonly callId: string }
  | { readonly _tag: "Memory"; readonly memoryId: string }
  | { readonly _tag: "Recall"; readonly query: string; readonly score: number }

export type ContextEdge =
  | { readonly _tag: "Replaces"; readonly from: string; readonly to: string }
  | { readonly _tag: "Summarizes"; readonly from: readonly string[]; readonly to: string }
```

**收益**：压缩/审计时可追溯"这条信息来自哪"；比线性数组更精确。

#### 6.1.5 事件与状态转换

```typescript
export type LoopEvent =
  | { readonly _tag: "UserMessage"; readonly content: string; readonly sessionId: string }
  | { readonly _tag: "ContextReady"; readonly messages: readonly Message[] }
  | { readonly _tag: "LLMResponse"; readonly response: LLMResult; readonly needsTools: boolean }
  | { readonly _tag: "ToolResults"; readonly results: readonly ToolResult[] }
  | { readonly _tag: "ContextOverflow"; readonly tokens: number; readonly limit: number }
  | { readonly _tag: "Interrupt"; readonly reason: InterruptReason }
  | { readonly _tag: "Resume"; readonly value: unknown; readonly interruptId: string }
  | { readonly _tag: "RetryAttempt"; readonly error: RetryableError }
  | { readonly _tag: "Complete"; readonly response: string }
  | { readonly _tag: "Fail"; readonly error: LoopError }

// 纯函数：状态转换
export const transition = (state: LoopState, event: LoopEvent): LoopState => {
  switch (state._tag) {
    case "Idle":
      if (event._tag === "UserMessage")
        return { _tag: "Preparing", input: { text: event.content, sessionId: event.sessionId }, turn: 1 }
      return state
    case "Preparing":
      if (event._tag === "ContextReady")
        return { _tag: "CallingLLM", messages: event.messages, turn: state.turn }
      return state
    case "CallingLLM":
      if (event._tag === "LLMResponse") {
        return event.needsTools
          ? { _tag: "ExecutingTools", pendingCalls: event.response.toolCalls, turn: state.turn + 1 }
          : { _tag: "Completed", result: { response: event.response.content } }
      }
      if (event._tag === "Interrupt")
        return { _tag: "Interrupted", reason: event.reason, interruptId: crypto.randomUUID() }
      return state
    case "Interrupted":
      if (event._tag === "Resume")
        return { _tag: "CallingLLM", messages: [], turn: 0 }  // 简化，实际需恢复上下文
      return state
    // ... 其他状态
  }
}
```

### 6.2 工具域（Tools）

#### 6.2.1 工具定义 ADT

```typescript
// packages/domain/src/tools/types.ts
export type ToolDefinition = {
  readonly id: string
  readonly description: string
  readonly parameters: Schema.Schema<any, any>     // Effect Schema
  readonly jsonSchema: JSONSchema7                  // 自动生成 [OPT-5]
  readonly execute: (args: unknown, ctx: ToolContext) => Effect.Effect<ToolResult, ToolError>
}

export type ToolCall = {
  readonly id: string
  readonly toolId: string
  readonly args: Readonly<Record<string, unknown>>
}

export type ToolResult =
  | { readonly _tag: "Success"; readonly content: string; readonly metadata?: Readonly<Record<string, unknown>> }
  | { readonly _tag: "Failure"; readonly error: ToolError }
```

#### 6.2.2 工具定义辅助函数 `[OPT-5]`

```typescript
// packages/domain/src/tools/define-tool.ts
import * as S from "@effect/schema/Schema"
import { toJsonSchema } from "@effect/schema/JSONSchema"

export const defineTool = <P extends S.Schema<any, any>>(
  id: string,
  description: string,
  paramsSchema: P,
  execute: (args: S.Schema.Type<P>, ctx: ToolContext) => Effect.Effect<ToolResult, ToolError>
): ToolDefinition => ({
  id,
  description,
  parameters: paramsSchema,
  jsonSchema: toJsonSchema(paramsSchema),  // 自动转 JSON Schema
  execute: (raw, ctx) => Effect.gen(function* () {
    const args = yield* S.decode(paramsSchema)(raw)  // 运行时校验
    return yield* execute(args, ctx)
  }),
})
```

#### 6.2.3 工具自动发现 `[OPT-15]`

约定 `*.tool.ts` 命名 + Bun glob import：

```typescript
// packages/application/src/tools/auto-discover.ts
const modules = import.meta.glob("./definitions/*.tool.ts", { eager: true })

export const autoDiscoverTools = (): readonly ToolDefinition[] =>
  Object.values(modules)
    .map((m: any) => m.default)
    .filter((t): t is ToolDefinition => t?.id != null)
```

### 6.3 记忆域（Memory）

#### 6.3.1 Dream 两阶段记忆 `[OPT-7]`

```typescript
// packages/domain/src/memory/types.ts
export type Observation = {
  readonly id: string
  readonly sessionId: string
  readonly content: string
  readonly createdAt: number
  readonly stage: "short" | "long"   // 短期 / 长期
}

export type Fact = {
  readonly id: string
  readonly content: string
  readonly source: string           // 来源 observation id
  readonly confidence: number
  readonly tags: readonly string[]
}

// 纯函数：从 observations 提取 facts（实际 LLM 调用在 application 层）
export const mergeFacts = (existing: readonly Fact[], newFacts: readonly Fact[]): readonly Fact[] => {
  // 用 id 去重；confidence 高的覆盖低的
  const map = new Map(existing.map(f => [f.id, f]))
  for (const f of newFacts) {
    const cur = map.get(f.id)
    if (!cur || cur.confidence < f.confidence) map.set(f.id, f)
  }
  return Array.from(map.values())
}
```

### 6.4 工作流域（Workflows）

#### 6.4.1 Channel 抽象 `[OPT-1]`

```typescript
// packages/domain/src/workflows/channel.ts

export type Channel<T>
  = { readonly _tag: "LastValue"; readonly current: T | undefined }
  | { readonly _tag: "Topic"; readonly messages: readonly T[] }
  | { readonly _tag: "Reducer"; readonly current: T; readonly reducer: (a: T, b: T) => T }
  | { readonly _tag: "Barrier"; readonly pending: ReadonlySet<string>; readonly value: T | undefined }

export const applyChannel = <T>(c: Channel<T>, update: T): Channel<T> => {
  switch (c._tag) {
    case "LastValue": return { ...c, current: update }
    case "Topic":     return { ...c, messages: [...c.messages, update] }
    case "Reducer":   return { ...c, current: c.reducer(c.current, update) }
    case "Barrier":   return c
  }
}
```

#### 6.4.2 变更类型分类 `[OPT-4]`

```typescript
// packages/domain/src/workflows/types.ts
export type ChangeType = "augment" | "refactor" | "remove" | "fix" | "perf"

export type Task = {
  readonly id: string
  readonly title: string
  readonly changeType: ChangeType
  readonly completed: boolean
  readonly specRef?: string         // 引用 Spec 制品 [OPT-3]
  readonly acceptanceCriteria?: readonly string[]
}

export type WorkflowGraph = {
  readonly nodes: readonly WorkflowNode[]
  readonly channels: Readonly<Record<string, Channel<unknown>>>
  readonly edges: readonly WorkflowEdge[]
}

export type WorkflowNode = {
  readonly id: string
  readonly task: Task
  readonly handler: string         // handler id
}
```

#### 6.4.3 Send API 并行委派 `[OPT-11]`

```typescript
// packages/domain/src/workflows/send.ts
export type Send = {
  readonly _tag: "Send"
  readonly nodeId: string
  readonly payload: unknown
}

// 纯函数：从一个节点返回多个 Send，触发并行执行
export const dispatchParallel = (tasks: readonly TaskSpec[]): readonly Send[] =>
  tasks.map(t => ({ _tag: "Send", nodeId: t.handlerId, payload: t.input }))
```

### 6.5 项目域（Projects）

#### 6.5.1 Spec SDD 四制品 `[OPT-3]`

```typescript
// packages/domain/src/projects/spec.ts
export type SpecArtifact =
  | { readonly _tag: "Proposal"; readonly content: string; readonly rationale: string }
  | { readonly _tag: "Specs"; readonly sections: readonly SpecSection[] }
  | { readonly _tag: "Design"; readonly decisions: readonly DesignDecision[] }
  | { readonly _tag: "Tasks"; readonly items: readonly TaskItem[] }

export type SpecSection = {
  readonly id: string
  readonly title: string
  readonly content: string
}

export type TaskItem = {
  readonly id: string               // "1.1"
  readonly title: string             // "Add theme context"
  readonly completed: boolean        // [x] / [ ]
  readonly changeType: ChangeType    // [OPT-4]
  readonly acceptanceCriteria?: readonly string[]
}

export type Spec = {
  readonly id: string
  readonly projectId: string
  readonly artifacts: readonly SpecArtifact[]
  readonly createdAt: number
  readonly updatedAt: number
}
```

#### 6.5.2 项目与 Spec 关系

```typescript
// packages/domain/src/projects/types.ts
export type Project = {
  readonly id: string
  readonly name: string
  readonly rootDir: string
  readonly activeSpecId?: string    // 当前活跃 Spec
  readonly createdAt: number
}

// delegate_task 接受 Spec 引用，而非自由文本
export const validateSpecForDelegate = (spec: Spec): Either.Either<SpecError, Spec> => {
  const hasProposal = spec.artifacts.some(a => a._tag === "Proposal")
  const hasTasks = spec.artifacts.some(a => a._tag === "Tasks")
  if (!hasProposal) return Either.left({ _tag: "MissingProposal" })
  if (!hasTasks) return Either.left({ _tag: "MissingTasks" })
  return Either.right(spec)
}
```

### 6.6 权限域（Permissions）

#### 6.6.1 基于 ChangeType 的策略 `[OPT-4]`

```typescript
// packages/domain/src/permissions/policy.ts
export type Decision =
  | { readonly _tag: "Allow" }
  | { readonly _tag: "Deny"; readonly reason: string }
  | { readonly _tag: "Ask"; readonly reason: string }

// 纯函数：基于变更类型 + persona 判定权限
export const policyForChange = (task: Task, persona: AgentPersona): Decision => {
  if (task.changeType === "remove" && !persona.canRemove)
    return { _tag: "Deny", reason: "Remove requires owner" }
  if (task.changeType === "refactor" && !persona.canRefactor)
    return { _tag: "Ask", reason: "Refactor needs approval" }
  return { _tag: "Allow" }
}

// 纯函数：路径白名单校验
export const policyForPath = (path: string, safeRoot: string): Decision => {
  const normalized = path.normalize(path)
  if (!normalized.startsWith(safeRoot))
    return { _tag: "Deny", reason: "Path outside safe root" }
  return { _tag: "Allow" }
}
```

### 6.7 错误 ADT（全局）

```typescript
// packages/domain/src/errors.ts
export type ButlerError =
  | LoopError
  | ToolError
  | MemoryError
  | WorkflowError
  | PermissionError
  | ConfigError

export type LoopError =
  | { readonly _tag: "LLMUnavailable"; readonly provider: string }
  | { readonly _tag: "ContextOverflow"; readonly tokens: number }
  | { readonly _tag: "MaxRetriesExceeded"; readonly attempts: number }

export type ToolError =
  | { readonly _tag: "NotFound"; readonly toolId: string }
  | { readonly _tag: "InvalidArgs"; readonly toolId: string; readonly errors: readonly string[] }
  | { readonly _tag: "ExecutionFailed"; readonly toolId: string; readonly cause: string }
  | { readonly _tag: "Timeout"; readonly toolId: string; readonly timeoutMs: number }

export type PermissionError =
  | { readonly _tag: "Denied"; readonly reason: string }
  | { readonly _tag: "Interrupted"; readonly interruptId: string }
```

---

## 七、端口与服务（Effect Tags）

`packages/contracts/src/services/` 定义所有 Effect Tag 接口。

### 7.1 核心服务 Tag

```typescript
// packages/contracts/src/services/llm.ts
export class LLMService extends Context.Tag("@butler/LLMService")<
  LLMService,
  {
    readonly complete: (req: LLMRequest) => Effect.Effect<LLMResponse, LLMError>
    readonly stream: (req: LLMRequest) => Stream.Stream<LLMChunk, LLMError>
  }
>() {}

// packages/contracts/src/services/database.ts
export class DatabaseService extends Context.Tag("@butler/DatabaseService")<
  DatabaseService,
  {
    readonly query: <T>(sql: string, params: readonly unknown[]) => Effect.Effect<T[], DbError>
    readonly execute: (sql: string, params: readonly unknown[]) => Effect.Effect<number, DbError>
  }
>() {}

// packages/contracts/src/services/eventstore.ts
export class EventStoreService extends Context.Tag("@butler/EventStoreService")<
  EventStoreService,
  {
    readonly append: (event: DomainEvent) => Effect.Effect<void, EventStoreError>
    readonly load: (aggregateId: string) => Effect.Effect<readonly DomainEvent[], EventStoreError>
    readonly subscribe: () => Stream.Stream<DomainEvent, EventStoreError>
  }
>() {}

// packages/contracts/src/services/vector.ts
export class VectorService extends Context.Tag("@butler/VectorService")<
  VectorService,
  {
    readonly embed: (text: string) => Effect.Effect<readonly number[], VectorError>
    readonly search: (query: readonly number[], k: number) => Effect.Effect<readonly VectorHit[], VectorError>
  }
>() {}
```

### 7.2 LoopInterrupt Tag `[OPT-2]`

```typescript
// packages/contracts/src/services/loop.ts
export type InterruptReason =
  | { readonly _tag: "ToolNeedsApproval"; readonly toolCall: ToolCall }
  | { readonly _tag: "UserInputRequired"; readonly prompt: string }
  | { readonly _tag: "ResourceLimit"; readonly resource: string }

export class LoopInterrupt extends Context.Tag("@butler/LoopInterrupt")<
  LoopInterrupt,
  {
    readonly interrupt: (reason: InterruptReason) => Effect.Effect<unknown>
    readonly isInterrupted: () => Effect.Effect<boolean>
  }
>() {}

// packages/contracts/src/services/command.ts
export type Command =
  | { readonly _tag: "Resume"; readonly value: unknown; readonly interruptId: string }
  | { readonly _tag: "Update"; readonly patch: Partial<LoopState> }
  | { readonly _tag: "Goto"; readonly node: string }
```

### 7.3 其他 Tag

```typescript
export class WeChatService extends Context.Tag("@butler/WeChatService")<WeChatService, { ... }> {}
export class McpService extends Context.Tag("@butler/McpService")<McpService, { ... }> {}
export class CacheService extends Context.Tag("@butler/CacheService")<CacheService, { ... }> {}
export class ObservabilityService extends Context.Tag("@butler/Observability")<ObservabilityService, { ... }> {}
```

### 7.4 Layer 组合

```typescript
// packages/contracts/src/layers/production.ts
export const ProductionLayer = Layer.mergeAll(
  DatabaseServiceLive,
  LLMServiceLive,
  EventStoreServiceLive,
  VectorServiceLive,
  WeChatServiceLive,
  McpServiceLive,
  CacheServiceLive,
  ObservabilityLive,
  LoopInterruptLive,
)

// packages/contracts/src/layers/test.ts
export const TestLayer = Layer.mergeAll(
  DatabaseServiceTest,  // in-memory
  LLMServiceTest,        // mock responses
  // ...
)
```

---

## 八、应用层：用例编排

`packages/application/src/` 用 `Effect.gen` 组合业务流程。

### 8.1 对话用例：run-loop

```typescript
// packages/application/src/conversation/run-loop.ts
export const runLoop = (input: UserInput) =>
  Effect.gen(function* () {
    const state = yield* stepPreparing(input)
    return yield* loop(state)
  }).pipe(
    Effect.withSpan("run-loop", { attributes: { sessionId: input.sessionId } })  // [OPT-17]
  )

const loop = (state: LoopState): Effect.Effect<LoopResult, LoopError> =>
  Effect.gen(function* () {
    switch (state._tag) {
      case "Completed": return state.result
      case "Failed":    return yield* Effect.fail(state.error)
      case "Interrupted": return yield* waitForResume(state)
      case "CallingLLM": {
        const resp = yield* callLlm(state.messages).pipe(
          Effect.withSpan("call-llm")
        )
        return yield* loop(transition(state, { _tag: "LLMResponse", response: resp, needsTools: resp.toolCalls.length > 0 }))
      }
      case "ExecutingTools": {
        const results = yield* executeTools(state.pendingCalls)
        return yield* loop(transition(state, { _tag: "ToolResults", results }))
      }
      // ...
    }
  })

// 工具执行可中断 [OPT-2]
const executeTools = (calls: readonly ToolCall[]) =>
  Effect.all(calls.map(executeWithApproval), { concurrency: "unbounded" })

const executeWithApproval = (call: ToolCall) =>
  Effect.gen(function* () {
    const decision = yield* checkPermissions(call)
    if (decision._tag === "Ask") {
      // 中断 Loop，等待 Owner 微信确认
      const userDecision = yield* LoopInterrupt.interrupt({
        _tag: "ToolNeedsApproval",
        toolCall: call,
      })
      if (userDecision === "deny") return deniedResult(call)
    }
    return yield* executeTool(call)
  })
```

### 8.2 工作用例：run-workflow

```typescript
// packages/application/src/workflows/run-workflow.ts
export const runWorkflow = (graph: WorkflowGraph, input: WorkflowInput) =>
  Effect.gen(function* () {
    const channels = initializeChannels(graph.channels)
    // 执行 DAG，按 Channel 变化触发下游节点
    const result = yield* executeNodes(graph.nodes, channels, input)
    return result
  }).pipe(Effect.withSpan("run-workflow"))

// 并行委派 [OPT-11]
const executeNodes = (nodes: readonly WorkflowNode[], channels: Channels, input: WorkflowInput) =>
  Effect.gen(function* () {
    // 拓扑排序，按依赖关系分组
    const levels = topologicalSort(nodes)
    for (const level of levels) {
      // 同层节点并行执行
      const sends = level.flatMap(n => dispatchIfReady(n, channels))
      if (sends.length > 0) {
        const results = yield* Effect.all(
          sends.map(s => Effect.fork(runNode(s))),
          { concurrency: "unbounded" }
        )
        // 用 Channel reducer 聚合
        for (const r of results) {
          yield* updateChannels(channels, r)
        }
      }
    }
  })
```

### 8.3 记忆用例：Dream 两阶段 `[OPT-7]`

```typescript
// packages/application/src/memory/store-observation.ts
// Phase 1: 会话中只写短期观察（快）
export const storeShortTerm = (obs: Observation) =>
  Effect.gen(function* () {
    const eventStore = yield* EventStoreService
    yield* eventStore.append({ type: "ObservationStored", payload: { ...obs, stage: "short" } })
  })

// packages/application/src/memory/consolidate.ts
// Phase 2: 会话结束后异步巩固（慢，由 outbox-worker 触发）
export const consolidate = (sessionId: string) =>
  Effect.gen(function* () {
    const observations = yield* loadSession(sessionId)
    // LLM 提取事实
    const facts = yield* extractFacts(observations)
    yield* storeLongTermFacts(facts)
    yield* updateProjection(facts)
  }).pipe(Effect.withSpan("memory-consolidate"))
```

### 8.4 项目用例：delegate-task

```typescript
// packages/application/src/projects/delegate-task.ts
export const delegateTask = (spec: Spec, scope: TaskScope) =>
  Effect.gen(function* () {
    // 验证 spec 完整性
    yield* Effect.fromEither(validateSpecForDelegate(spec))
    // 按 tasks.md 顺序执行
    const tasks = getTaskItems(spec)
    for (const item of tasks) {
      if (!item.completed) {
        yield* executeTaskItem(item, scope)
      }
    }
  }).pipe(Effect.withSpan("delegate-task"))
```

---

## 九、基础设施层：命令式外壳

`packages/infrastructure/src/` 实现 Port 接口。

### 9.1 数据库 + Drizzle

```typescript
// packages/infrastructure/src/database/schema.ts
import { pgTable, uuid, varchar, text, timestamp, integer, jsonb, boolean } from "drizzle-orm/pg-core"

export const sessions = pgTable("sessions", {
  id: uuid("id").primaryKey().defaultRandom(),
  projectId: uuid("project_id").notNull(),
  createdAt: timestamp("created_at").defaultNow().notNull(),
})

export const events = pgTable("events", {
  id: uuid("id").primaryKey().defaultRandom(),
  aggregateId: varchar("aggregate_id").notNull(),
  type: varchar("type").notNull(),
  payload: jsonb("payload").notNull(),
  version: integer("version").notNull(),
  timestamp: timestamp("timestamp").defaultNow().notNull(),
})

export const facts = pgTable("facts", {
  id: uuid("id").primaryKey().defaultRandom(),
  content: text("content").notNull(),
  source: varchar("source").notNull(),
  confidence: integer("confidence").notNull(),
  tags: jsonb("tags").notNull(),
  createdAt: timestamp("created_at").defaultNow().notNull(),
})
```

### 9.2 LLM 客户端 + 重试

```typescript
// packages/infrastructure/src/llm/client.ts
export const LLMServiceLive = Layer.effect(LLMService, Effect.gen(function* () {
  return LLMService.of({
    complete: (req) =>
      Effect.retry(callProvider(req), Schedule.exponential("1 seconds").pipe(Schedule.upTo("30 seconds"))),
    stream: (req) => Stream.fromEffect(callProvider(req)),
  })
}))

const callProvider = (req: LLMRequest) =>
  Effect.gen(function* () {
    const provider = yield* selectProvider(req.model)
    // Vercel AI SDK 调用
    const result = yield* Effect.tryPromise(() => generateCompletion(provider, req))
    return result
  })
```

### 9.3 MCP 动态发现 + 缓存失效 `[OPT-6]`

```typescript
// packages/infrastructure/src/mcp/manager.ts
export const McpServiceLive = Layer.effect(McpService, Effect.gen(function* () {
  const servers = new Map<string, { conn: McpConnection; tools: readonly ToolDefinition[]; version: number }>()

  return McpService.of({
    connect: (config) =>
      Effect.gen(function* () {
        const conn = yield* createConnection(config)
        const tools = yield* conn.listTools()
        servers.set(config.id, { conn, tools, version: 0 })
      }),

    getTools: () => Effect.sync(() =>
      Array.from(servers.values()).flatMap(s => s.tools)
    ),

    onToolListChanged: (serverId) =>
      Effect.sync(() => {
        const s = servers.get(serverId)
        if (s) s.version++  // 触发缓存失效
      }),
  })
}))
```

### 9.4 Hybrid EventStore（事件 + Snapshot）`[OPT-12]`

```typescript
// packages/infrastructure/src/eventstore/hybrid-store.ts
const SNAPSHOT_EVERY = 100

export const EventStoreServiceLive = Layer.effect(EventStoreService, Effect.gen(function* () {
  let eventCount = 0

  return EventStoreService.of({
    append: (event) =>
      Effect.gen(function* () {
        yield* appendEvent(event)
        eventCount++
        if (eventCount % SNAPSHOT_EVERY === 0) {
          const state = yield* rehydrate()
          yield* saveSnapshot(state)
        }
      }),

    load: (id) =>
      Effect.gen(function* () {
        const snapshot = yield* loadLatestSnapshot(id)
        const events = yield* loadEventsAfter(snapshot.version)
        return applyEvents(snapshot.state, events)
      }),

    subscribe: () => Stream.fromQueue(globalEventQueue),
  })
}))
```

### 9.5 RelativeIndenter + 多策略 patch `[OPT-13]`

```typescript
// packages/infrastructure/src/edit/apply-patch.ts
export const applyPatch = (original: string, patch: Patch) =>
  Effect.gen(function* () {
    const r1 = tryExactMatch(original, patch)
    if (r1._tag === "Right") return r1.right

    const r2 = tryRelativeIndent(original, patch)
    if (r2._tag === "Right") return r2.right

    const r3 = yield* tryDiffMatchPatch(original, patch)
    if (r3._tag === "Right") return r3.right

    return yield* Effect.fail({ _tag: "PatchApplyFailed", patch })
  })
```

### 9.6 PageRank repo-map `[OPT-14]`

```typescript
// packages/infrastructure/src/dev-engine/build-repo-map.ts
export const buildRepoMap = (rootDir: string) =>
  Effect.gen(function* () {
    const files = yield* scanSourceFiles(rootDir)
    const symbols = yield* extractSymbols(files)
    const graph = buildReferenceGraph(symbols)
    const ranked = pageRank(graph)
    return formatRepoMap(ranked.slice(0, 200))
  }).pipe(Effect.withSpan("build-repo-map"))
```

---

## 十、事件溯源 + CQRS

### 10.1 事件流

所有状态变更通过事件流记录：

```typescript
// packages/domain/src/events.ts
export type DomainEvent =
  | { readonly _tag: "SessionStarted"; readonly sessionId: string; readonly projectId: string }
  | { readonly _tag: "UserMessageReceived"; readonly sessionId: string; readonly content: string }
  | { readonly _tag: "LLMResponseGenerated"; readonly sessionId: string; readonly response: string }
  | { readonly _tag: "ToolExecuted"; readonly sessionId: string; readonly toolCall: ToolCall; readonly result: ToolResult }
  | { readonly _tag: "ObservationStored"; readonly observation: Observation }
  | { readonly _tag: "FactExtracted"; readonly fact: Fact }
  | { readonly _tag: "WorkflowStepCompleted"; readonly workflowId: string; readonly nodeId: string }
  | { readonly _tag: "ProjectCreated"; readonly projectId: string; readonly name: string }
```

### 10.2 CQRS 读写分离

```typescript
// 写模型：Command → Event
export const handleCommand = (cmd: Command, state: LoopState) =>
  Effect.gen(function* () {
    const event = commandToEvent(cmd, state)
    yield* EventStoreService.append(event)
    return event
  })

// 读模型：Event → Projection
export const buildProjection = (events: readonly DomainEvent[]): SessionView => {
  // 纯函数：从事件流重建读模型
  return events.reduce(applyEvent, initialState)
}

// packages/infrastructure/src/eventstore/projections/
export const SessionProjection = {
  name: "session-view",
  handle: (event: DomainEvent, view: SessionView): SessionView => {
    switch (event._tag) {
      case "SessionStarted":
        return { ...view, sessionId: event.sessionId, projectId: event.projectId }
      case "UserMessageReceived":
        return { ...view, messages: [...view.messages, event] }
      // ...
    }
  },
}
```

### 10.3 Outbox Pattern（双写一致性）

```typescript
// apps/worker/src/outbox-worker.ts
const processOutbox = Effect.gen(function* () {
  const pending = yield* loadPendingOutboxEntries()
  for (const entry of pending) {
    yield* publishToWeChat(entry.payload)
    yield* markOutboxProcessed(entry.id)
  }
}).pipe(
  Effect.forever,
  Effect.withSpan("outbox-worker")
)
```

---

## 十一、网关层

### 11.1 入站 EventBus `[OPT-9]`

```typescript
// apps/gateway/src/inbound.ts
import { Stream, Queue } from "effect"
import { Hono } from "hono"

export const startGateway = Effect.gen(function* () {
  const inboundQueue = yield* Queue.unbounded<InboundMessage>()

  // iLink webhook → 入队（快）
  const hono = new Hono()
  hono.post("/wechat", async (c) => {
    const msg = await c.req.json()
    await Effect.runPromise(Queue.offer(inboundQueue, msg))
    return c.json({ ok: true })
  })

  // 后台消费者（慢）
  yield* Effect.fork(
    Stream.fromQueue(inboundQueue).pipe(
      Stream.run(msg => runAgentLoop(msg))
    )
  )

  Bun.serve({ port: 3000, fetch: hono.fetch })
})
```

**收益**：网关 P99 延迟降到 ms 级；Loop 慢不影响接收；天然背压。

### 11.2 出站消息

```typescript
// apps/gateway/src/outbound.ts
export const sendToWeChat = (msg: OutboundMessage) =>
  Effect.gen(function* () {
    const wechat = yield* WeChatService
    // 入 outbox，由 worker 异步发送
    yield* appendOutbox(msg)
  })
```

---

## 十二、配置管理

### 12.1 单一 Schema 替代 200+ 环境变量

```typescript
// packages/contracts/src/config.ts
import * as S from "@effect/schema/Schema"

export const ConfigSchema = S.struct({
  butler: S.struct({
    name: S.string,
    ownerName: S.string,
    logLevel: S.literal("debug", "info", "warn", "error"),
  }),
  llm: S.struct({
    defaultProvider: S.string,
    providers: S.record(S.string, ProviderConfig),
    fallback: FallbackConfig,
  }),
  gateway: S.struct({
    port: S.number,
    wechatToken: S.string,
    wechatAccountId: S.string,
    handlerTimeout: S.number,
    maxSessions: S.number,
  }),
  memory: S.struct({
    semanticEnabled: S.boolean,
    embeddingProvider: S.string,
    embeddingModel: S.string,
  }),
  tools: S.struct({
    safeRoot: S.string,
    scope: S.literal("environment", "project"),
  }),
})

export type Config = S.Schema.Type<typeof ConfigSchema>
```

### 12.2 配置优先级

| 层级 | 来源 | 说明 |
|------|------|------|
| 1 | 进程 env | systemd `Environment=`、shell `export` |
| 2 | `.env` | 仓库根 |
| 3 | `~/.butler/config.yaml` | 结构化段 |
| 4 | 代码默认值 | `packages/contracts/src/defaults.ts` |

### 12.3 加载流程

```typescript
// packages/contracts/src/config-loader.ts
export const loadConfig = Effect.gen(function* () {
  const env = yield* loadEnv()
  const yaml = yield* loadYaml("~/.butler/config.yaml").pipe(Effect.catchAll(() => Effect.succeed({})))
  const merged = mergeConfigs(env, yaml, defaults)
  return yield* S.decode(ConfigSchema)(merged)
})
```

---

## 十三、测试策略

### 13.1 测试金字塔

```
┌─────────────────────────────────┐
│  E2E（<10%）                     │  apps/ 端到端
│  ─────────────────              │  真实 DB + LLM + 微信 mock
├─────────────────────────────────┤
│  集成测试（20%）                  │  infrastructure/
│  ─────────────────              │  真实 DB / HTTP
├─────────────────────────────────┤
│  单元测试（70%）                  │  domain/ + application/
│  ─────────────────              │  domain/ 零 mock
│                                 │  application/ Mock Layer
└─────────────────────────────────┘
```

### 13.2 domain/ 测试：纯函数 + 代数定律

```typescript
// packages/domain/tests/conversation/transition.test.ts
import { describe, it, expect } from "bun:test"

describe("transition", () => {
  it("Idle + UserMessage → Preparing", () => {
    const next = transition({ _tag: "Idle" }, { _tag: "UserMessage", content: "hi", sessionId: "s1" })
    expect(next._tag).toBe("Preparing")
  })

  // 代数定律：状态转换可重放
  it("replay events produces same state", () => {
    const events = [/* ... */]
    const state = events.reduce(transition, { _tag: "Idle" })
    const replayed = events.reduce(transition, { _tag: "Idle" })
    expect(replayed).toEqual(state)
  })
})

// 代数定律：Channel reducer 结合律
describe("applyChannel reducer associativity", () => {
  it("(a + b) + c == a + (b + c)", () => {
    const reducer = (a: number, b: number) => a + b
    const c1: Channel<number> = { _tag: "Reducer", current: 0, reducer }
    const left = applyChannel(applyChannel(applyChannel(c1, 1), 2), 3)
    const right = applyChannel(applyChannel(applyChannel(c1, 3), 2), 1)
    expect(left.current).toEqual(right.current)
  })
})
```

### 13.3 application/ 测试：Mock Layer

```typescript
// packages/application/tests/conversation/run-loop.test.ts
import { TestLayer } from "@butler/contracts/layers/test"

const MockLLM = LLMService.of({
  complete: () => Effect.succeed({ content: "hello", toolCalls: [] }),
  stream: () => Stream.empty,
})

const testLayer = Layer.mergeAll(TestLayer, Layer.succeed(LLMService, MockLLM))

it("runs simple loop without tools", async () => {
  await Effect.runPromise(
    runLoop({ text: "hi", sessionId: "s1" }).pipe(Effect.provide(testLayer))
  )
})
```

### 13.4 infrastructure/ 测试：真实 DB

```typescript
// packages/infrastructure/tests/eventstore.test.ts
import { setupTestDb, teardownTestDb } from "../helpers"

beforeEach(async () => await setupTestDb())
afterEach(async () => await teardownTestDb())

it("appends and loads events", async () => {
  await Effect.runPromise(
    Effect.gen(function* () {
      const store = yield* EventStoreService
      yield* store.append({ type: "TestEvent", payload: {} })
      const events = yield* store.load("agg-1")
      expect(events).toHaveLength(1)
    }).pipe(Effect.provide(EventStoreServiceLive))
  )
})
```

---

## 十四、可观测性

### 14.1 Effect 内置 tracing `[OPT-17]`

```typescript
// 用 Effect.withSpan 自动埋点，零成本接入 OpenTelemetry
export const runLoop = (input: UserInput) =>
  Effect.gen(function* () { ... }).pipe(
    Effect.withSpan("run-loop", { attributes: { sessionId: input.sessionId } })
  )

// 自定义业务事件
yield* Effect.logAnnotated("tool executed", {
  toolId: call.id,
  duration: elapsed,
  success: true,
})
```

### 14.2 三层观测

| 层 | 工具 | 用途 |
|----|------|------|
| Metrics | Effect metrics + Prometheus | QPS、延迟、错误率 |
| Tracing | Effect.withSpan + Jaeger | 请求链路 |
| Logging | Effect.logAnnotated + 结构化日志 | 业务事件 |

### 14.3 健康检查

```typescript
// apps/gateway/src/routes/health.ts
hono.get("/health", () => Effect.runPromise(
  Effect.gen(function* () {
    const db = yield* DatabaseService
    const ok = yield* db.query("SELECT 1", []).pipe(Effect.either)
    return ok._tag === "Right" ? Response.json({ status: "ok" }) : Response.json({ status: "degraded" }, { status: 503 })
  })
))
```

---

## 十五、迁移计划：绞杀者模式

### 15.1 总体策略

**不一次性重写**，而是通过绞杀者模式（Strangler Fig）逐步替换 v4 的 Service 层：

```
v4 Gateway ──→ v4 Service ──→ v4 DB           Phase 0：原状
       │
       └──→ Anti-Corruption Layer ──→ v5 domain
                                              Phase 1：ACL 接入

v4 Gateway ──→ v4 Service ──→ v4 DB
       │              ↑ 镜像
       └──→ v5 Gateway ──→ v5 application ──→ v5 DB
                                              Phase 2：并行运行

v4 Gateway ──→ v5 Gateway ──→ v5 application ──→ v5 DB
                                              Phase 3：流量切换

(retired) ──→ v5 Gateway ──→ v5 application ──→ v5 DB
                                              Phase 4：v4 退役
```

### 15.2 反腐层（Anti-Corruption Layer）

```typescript
// packages/acl/src/v4-adapter.ts
export const V4Adapter = Layer.effect(V4Service, Effect.gen(function* () {
  // 调用 v4 的 HTTP API，转换为 v5 的 domain 类型
  return V4Service.of({
    getSession: (id) =>
      Effect.gen(function* () {
        const raw = yield* callV4Api(`/sessions/${id}`)
        return mapV4SessionToV5(raw)  // 纯函数转换
      }),
  })
}))
```

### 15.3 双写一致性：Outbox Pattern

```typescript
// v5 写入时同时写入 v4 DB（通过 ACL）
const dualWrite = (event: DomainEvent) =>
  Effect.gen(function* () {
    yield* EventStoreService.append(event)        // 写 v5
    yield* V4Adapter.syncEvent(event)             // 同步 v4
  })
```

### 15.4 数据迁移

| 数据源 | 目标 | 迁移脚本 |
|--------|------|---------|
| ChromaDB | pgvector | `scripts/migrate-chroma-to-pgvector.ts` |
| SQLite（v4 会话） | PostgreSQL | `scripts/migrate-sqlite-to-postgres.ts` |
| 文件系统记忆 | PostgreSQL facts 表 | `scripts/migrate-memory-to-facts.ts` |

### 15.5 影子模式验证

```typescript
// 流量复制：生产流量同时发到 v4 和 v5，对比结果
const shadowMode = (request: Request) =>
  Effect.gen(function* () {
    const v4Result = yield* callV4(request)
    const v5Result = yield* callV5(request).pipe(Effect.either)
    yield* compareResults(v4Result, v5Result)  // 不返回 v5 结果
    return v4Result
  })
```

---

## 十六、实施路线图

### Phase 1：核心域 + POC（Week 1-4）

| 周 | 任务 | 产出 | 优化项 |
|----|------|------|--------|
| 1 | 搭建 Monorepo + domain/ 对话域 | ADT + 纯函数 + 测试 | `[OPT-8]` `[OPT-10]` |
| 2 | Spec SDD + 变更类型 | `domain/projects/spec.ts` + `workflows/types.ts` | `[OPT-3]` `[OPT-4]` |
| 3 | Channel 抽象 + interrupt/resume | `domain/workflows/channel.ts` + `contracts/services/loop.ts` | `[OPT-1]` `[OPT-2]` |
| 4 | contracts/ + application/ 对话用例 + POC 验证 | Effect Layer + Agent Loop | — |

**POC 验证点**：
- ContextPipeline 组合是否优雅
- LLM 重试链是否可用
- interrupt/resume 是否能暂停整个 Loop

### Phase 2：完整域（Week 5-8）

| 周 | 任务 | 产出 | 优化项 |
|----|------|------|--------|
| 5 | 工具域 + 工具 Schema 自动生成 + 自动发现 | `defineTool` + `auto-discover.ts` | `[OPT-5]` `[OPT-15]` |
| 6 | 记忆域 + Dream 两阶段 | 短期/长期分离 | `[OPT-7]` |
| 7 | 工作流域 + Send API 并行委派 | `dispatch-parallel.ts` | `[OPT-11]` |
| 8 | 集成测试 + 性能调优 | 全域测试通过 | — |

### Phase 3：基础设施 + 网关（Week 9-12）

| 周 | 任务 | 产出 | 优化项 |
|----|------|------|--------|
| 9 | Hybrid EventStore + MCP 动态发现 | `hybrid-store.ts` + `mcp/manager.ts` | `[OPT-6]` `[OPT-12]` |
| 10 | RelativeIndenter + PageRank repo-map | edit/ + dev-engine/ | `[OPT-13]` `[OPT-14]` |
| 11 | 网关 EventBus + 微信适配 | `apps/gateway/` | `[OPT-9]` |
| 12 | Docker + CI/CD | 容器化 + 自动部署 | — |

### Phase 4：迁移 + 收尾（Week 13-16）

| 周 | 任务 | 产出 | 优化项 |
|----|------|------|--------|
| 13 | 数据迁移脚本 + ACL | ChromaDB → pgvector | — |
| 14 | 影子模式 + 校验 | 并行运行验证 | — |
| 15 | ContextGraph + tracing + ArtifactGraph | 可观测性完善 | `[OPT-16]` `[OPT-17]` `[OPT-18]` |
| 16 | 流量切换 + v4 退役 | 100% 切到新系统 | — |

**总计**：16 周（4 个月），含完整测试和文档。

---

## 十七、验证标准

每条优化建议落地后需满足：

| 类型 | 验证标准 |
|------|---------|
| **纯函数**（`[OPT-1]` `[OPT-4]` `[OPT-8]` `[OPT-10]`） | 单元测试零 mock；代数定律（associativity/identity）成立 |
| **Effect Layer**（`[OPT-2]` `[OPT-5]` `[OPT-6]` `[OPT-7]` `[OPT-9]`） | Mock Layer 可替换；运行时 Layer 组合通过 |
| **基础设施**（`[OPT-12]` `[OPT-13]`） | 集成测试用真实 DB/文件系统；性能基准达标 |
| **流程类**（`[OPT-3]` `[OPT-11]` `[OPT-15]`） | 端到端测试覆盖完整流程；失败可回滚 |
| **可观测性**（`[OPT-16]` `[OPT-17]` `[OPT-18]`） | trace 可在 Jaeger 看到；artifact 状态可恢复 |

### 17.1 POC 验收标准

- **ContextPipeline**：组合 5 个纯函数，性能 < 1ms
- **LLM 重试**：3 次失败后正确降级到 fallback provider
- **interrupt/resume**：工具调用暂停 60s 后正确恢复
- **Channel reducer**：4 个并行节点结果正确合并
- **Spec SDD**：`delegate_task` 接受 Spec 引用，按 tasks.md 顺序执行

### 17.2 性能基准

| 指标 | v4 | v5 目标 |
|------|-----|---------|
| 初始内存 | 15MB | <5MB |
| 网关 P99 延迟 | 500ms | <50ms（队列模式） |
| 单轮 Loop | 2-5s | 1-3s |
| 事件回放（1000 事件） | N/A | <100ms（Hybrid Store） |

---

## 十八、不采纳设计

| 设计 | 来源 | 不采纳原因 |
|------|------|-----------|
| Scala + ZIO | ZIO 生态 | 单语言团队成本；Effect-TS 已足够 |
| 全量 Event Sourcing（无 snapshot） | 理论纯度 | 长会话回放慢；用 `[OPT-12]` Hybrid Store |
| WASM 沙箱 | 强隔离 | 部署复杂；dev_engine 用进程级隔离即可 |
| Python 子进程网关 | v4 兼容 | v5 完全重写，不需要兼容 v4 网关 |
| 类继承体系 | OOP 习惯 | 与 FC/IS 冲突；用 Effect Layer + 函数组合 |
| 隐式异常（throw） | JS 习惯 | 违反"错误是值"原则；用 `Effect.fail` + ADT |
| RxJS | 响应式扩展 | Effect Stream 已是超集 |
| 手动 Reader Monad DI | fp-ts 风格 | Effect Layer 原生支持 |

---

## 十九、附录：18 条优化建议索引

| # | 优先级 | 标题 | 章节定位 | 来源 |
|---|-------|------|---------|------|
| 1 | P0 | Channel 抽象 | §6.4.1 | LangGraph |
| 2 | P0 | interrupt/resume + Command API | §7.2 | LangGraph |
| 3 | P0 | Spec SDD 四制品 | §6.5.1 | spec-kit |
| 4 | P0 | 变更类型分类 | §6.4.2 | OpenSpec |
| 5 | P1 | 工具 Schema 自动转 JSON Schema | §6.2.2 | OpenCode |
| 6 | P1 | MCP 动态发现 + 缓存失效 | §9.3 | Cline |
| 7 | P1 | Dream 两阶段记忆巩固 | §6.3 + §8.3 | nanobot |
| 8 | P1 | 双策略压缩 | §6.1.2 | Cline |
| 9 | P1 | 轻量 EventBus | §11.1 | nanobot |
| 10 | P2 | AgentPersona 三元组 | §6.1.3 | crewAI |
| 11 | P2 | Send API 并行委派 | §6.4.3 + §8.2 | LangGraph |
| 12 | P2 | DeltaChannel 增量检查点 | §9.4 | LangGraph |
| 13 | P2 | RelativeIndenter + 多策略 patch | §9.5 | aider |
| 14 | P2 | PageRank repo-map | §9.6 | aider |
| 15 | P2 | 工具自动发现 | §6.2.3 | nanobot |
| 16 | P3 | ContextGraph 有向图 | §6.1.4 | Gemini-CLI |
| 17 | P3 | Effect.withSpan 自动埋点 | §14.1 | LangGraph |
| 18 | P3 | ArtifactGraph 文件存在性推断 | （后置） | OpenSpec |

完整建议详见 [`butler-v5-optimization-from-projects-2026-07-30.md`](butler-v5-optimization-from-projects-2026-07-30.md)。

---

## 二十、参考文档

### Butler v5 文档族
- [`butler-v5-functional-architecture-2026-07-30.md`](butler-v5-functional-architecture-2026-07-30.md) — 原始主架构（已被本文档整合并扩展）
- [`butler-v5-optimization-from-projects-2026-07-30.md`](butler-v5-optimization-from-projects-2026-07-30.md) — 18 条优化建议详述
- [`functional-architecture-migration-plan-2026-07-30.md`](functional-architecture-migration-plan-2026-07-30.md) — 迁移主方案
- [`strangler-fig-migration-guide-2026-07-30.md`](strangler-fig-migration-guide-2026-07-30.md) — 绞杀者模式指南
- [`functional-migration-supplement-2026-07-30.md`](functional-migration-supplement-2026-07-30.md) — 数据迁移补充

### 外部项目解析
- [OpenHands项目解析.md](file:///home/ailearn/githubpro/项目解析/OpenHands项目解析.md)
- [Cline项目解析.md](file:///home/ailearn/githubpro/项目解析/Cline项目解析.md)
- [LangGraph项目解析.md](file:///home/ailearn/githubpro/项目解析/LangGraph项目解析.md)
- [spec-kit项目解析.md](file:///home/ailearn/githubpro/项目解析/spec-kit项目解析.md)
- [OpenSpec项目解析.md](file:///home/ailearn/githubpro/项目解析/OpenSpec项目解析.md)
- [nanobot项目解析.md](file:///home/ailearn/githubpro/项目解析/nanobot项目解析.md)
- [crewAI项目解析.md](file:///home/ailearn/githubpro/项目解析/crewAI项目解析.md)
- [aider项目解析.md](file:///home/ailearn/githubpro/项目解析/aider项目解析.md)
- [Gemini-CLI项目解析.md](file:///home/ailearn/githubpro/项目解析/Gemini-CLI项目解析.md)
- [opencode项目解析.md](file:///home/ailearn/githubpro/项目解析/opencode项目解析.md)

### Butler v4 参考文档
- [`docs/architecture/v4-architecture.md`](../architecture/v4-architecture.md) — v4 九层架构
- [`docs/architecture/v4-layer-model.md`](../architecture/v4-layer-model.md) — v4 分层模型
- [`docs/config/reference.md`](../config/reference.md) — v4 配置参考

---

**文档状态**：完整设计方案 SSOT，覆盖架构/领域/端口/基础设施/迁移/路线图/验证
**下次更新触发**：POC 验证完成、Phase 1 实施后回顾

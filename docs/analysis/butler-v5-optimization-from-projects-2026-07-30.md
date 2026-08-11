# Butler v5 — 来自外部高星项目的优化建议

> **日期**：2026-07-30
> **定位**：对 [`butler-v5-functional-architecture-2026-07-30.md`](butler-v5-functional-architecture-2026-07-30.md) 的补充优化建议，**不替换**主文档
> **来源**：`~/githubpro/项目解析/` 下 9 个高星项目解析文档
> **使用方式**：按优先级挑选实施；每条建议标注"主文档对应章节"，便于回写
> **核心约束**：仍是 TypeScript + Effect-TS + FC/IS + CQRS + Event Sourcing；不引入 Scala/WASM

---

## 一、来源项目与价值定位

| 项目 | 主要价值 | 对 Butler v5 的贡献域 |
|------|---------|---------------------|
| **LangGraph** | Pregel BSP 模型、Channel 抽象、interrupt/resume、DeltaChannel | 工作流编排、Loop 中断恢复 |
| **OpenCode** | Layer Node 依赖图、Effect Schema 工具定义 | 工具系统、依赖注入 |
| **OpenHands** | 事件流驱动、Agent 状态机、沙箱 | 领域建模、运行时 |
| **Cline** | Checkpoint + Git stash 回滚、MCP 动态发现、双策略压缩 | 工具审批、上下文管理 |
| **spec-kit** | SDD 四阶段、Bundle DAG、AI 守卫 | 项目待办、防跑偏 |
| **OpenSpec** | 变更类型分类（augment/refactor/remove）、ArtifactGraph 拓扑推断 | 工作流类型、状态恢复 |
| **nanobot** | Dream 两阶段记忆、消息总线、工具自动发现 | 记忆系统、网关解耦 |
| **crewAI** | Role/Goal/Backstory 三元组、Hierarchical 委派 | Agent persona、多 Agent 协作 |
| **aider** | RelativeIndenter、PageRank repo-map、多策略 patch | dev_engine 编辑/导航 |
| **Gemini-CLI** | ContextGraph 有向图、声明式工具构建器 | 上下文可审计性 |

---

## 二、优化建议总览（按优先级）

| # | 优先级 | 标题 | 主文档章节 | 来源 |
|---|-------|------|-----------|------|
| 1 | **P0** | Channel 抽象（替代简单 DAG reducer） | §四 工作流域 | LangGraph |
| 2 | **P0** | interrupt/resume 原语 + Command API | §五 端口与服务 | LangGraph |
| 3 | **P0** | Spec 驱动开发四制品（proposal/specs/design/tasks） | §四 项目域（新增） | spec-kit |
| 4 | **P0** | 变更类型分类（augment/refactor/remove/fix） | §四 工作流域 | OpenSpec |
| 5 | **P1** | 工具 Schema 自动转 JSON Schema | §五 工具 Port | OpenCode |
| 6 | **P1** | MCP 动态发现 + 工具缓存失效 | §七 基础设施 | Cline |
| 7 | **P1** | Dream 两阶段记忆巩固 | §四 记忆域 | nanobot |
| 8 | **P1** | 双策略压缩（truncate + summarize） | §四 对话域 | Cline |
| 9 | **P1** | 轻量 EventBus（Effect Stream） | §九 网关层 | nanobot |
| 10 | **P2** | AgentPersona（role/goal/backstory） | §四 对话域（新增） | crewAI |
| 11 | **P2** | Send API 并行委派 + Channel reducer 聚合 | §六 应用层 | LangGraph |
| 12 | **P2** | DeltaChannel 增量检查点 | §七 事件存储 | LangGraph |
| 13 | **P2** | RelativeIndenter + 多策略 patch 应用器 | §七 dev_engine | aider |
| 14 | **P2** | PageRank repo-map 构建 | §六 dev-engine 用例 | aider |
| 15 | **P2** | 工具自动发现（命名约定 + 装饰器） | §五 工具 Port | nanobot |
| 16 | **P3** | ContextGraph 有向图（带 provenance） | §四 对话域 | Gemini-CLI |
| 17 | **P3** | Effect.withSpan 自动埋点 + LangSmith 风格 tracing | §七 可观测性 | LangGraph |
| 18 | **P3** | ArtifactGraph 文件存在性推断（状态恢复兜底） | §六 工作用例 | OpenSpec |

---

## 三、P0 优化建议（必须实施）

### #1 Channel 抽象（LangGraph）

**LangGraph 做法**：
- 用图（节点+边+Channel）建模工作流，每个节点签名 `State -> Partial<State>`
- Channel 类型化：`LastValue<T>`（最新值）、`Topic<T>`（pub/sub）、`BinaryOperatorAggregate<T>`（reducer 聚合）、`NamedBarrierValue`（屏障等待）
- 多分支并行节点的状态合并由 reducer 自动处理，不是手工 union

**Butler v5 现状**：
- 工作流域用纯 DAG + 拓扑排序（`domain/workflows/dag.ts`），节点结果靠手工合并
- `LoopState` 是单一状态机，无法表达"同时多个分支在跑"

**建议改进**：
在 `packages/domain/workflows/` 增加 Channel 类型：

```typescript
// packages/domain/src/workflows/channel.ts
export type Channel<T>
  = { readonly _tag: "LastValue"; readonly current: T | undefined }
  | { readonly _tag: "Topic"; readonly messages: readonly T[] }
  | { readonly _tag: "Reducer"; readonly current: T; readonly reducer: (a: T, b: T) => T }
  | { readonly _tag: "Barrier"; readonly pending: ReadonlySet<string>; readonly value: T | undefined }

// 纯函数：apply channel update
export const applyChannel = <T>(c: Channel<T>, update: T): Channel<T> => {
  switch (c._tag) {
    case "LastValue": return { ...c, current: update }
    case "Topic":     return { ...c, messages: [...c.messages, update] }
    case "Reducer":   return { ...c, current: c.reducer(c.current, update) }
    case "Barrier":   return c // 屏障不变，等显式 release
  }
}
```

工作流执行器从"线性 DAG"升级为"Channel-driven Graph"：
```typescript
// packages/application/src/workflows/run-workflow.ts
export const runWorkflow = (graph: WorkflowGraph, input: WorkflowInput) =>
  Effect.gen(function* () {
    const channels = initializeChannels(graph.channels)
    const fiber = yield* Effect.fork(executeNodes(graph.nodes, channels))
    // 节点输出自动 applyChannel，下游节点按 Channel 变化触发
  })
```

**收益**：并行分支的状态合并从手工变声明式；为 #11 Send API 并行委派铺路。

---

### #2 interrupt/resume 原语 + Command API（LangGraph）

**LangGraph 做法**：
- `interrupt(value)` 抛 `GraphInterrupt` 暂停整个图执行，状态持久化到 checkpoint
- `Command(resume=value)` 从断点恢复，`interrupt()` 返回用户提供的值
- `StateSnapshot` 可任意时刻检查/修改图状态

**Butler v5 现状**：
- 只有 `ApprovalStore` Port，工具调用前查询审批
- 没有"暂停整个 Loop Effect"的机制，工具等待审批时整个 Fiber 阻塞

**建议改进**：
在 `packages/contracts/src/services/loop.ts` 增加 Interrupt Tag：

```typescript
// packages/contracts/src/services/loop.ts
export class LoopInterrupt extends Context.Tag("@butler/LoopInterrupt")<
  LoopInterrupt,
  {
    // 暂停当前 Loop，等待外部 Command.resume
    readonly interrupt: (reason: InterruptReason) => Effect.Effect<ResumeValue>
    // 查询当前是否处于中断态
    readonly isInterrupted: () => Effect.Effect<boolean>
  }
>() {}

// packages/domain/src/conversation/command.ts
export type Command =
  | { readonly _tag: "Resume"; readonly value: unknown; readonly interruptId: string }
  | { readonly _tag: "Update"; readonly patch: Partial<LoopState> }
  | { readonly _tag: "Goto"; readonly node: string }
```

工具执行可主动中断：
```typescript
// packages/application/src/tools/dispatch-tool.ts
const executeWithApproval = (call: ToolCall) =>
  Effect.gen(function* () {
    const needsApproval = yield* checkPermissions(call)
    if (needsApproval) {
      // 中断 Loop，把控制权交回调用者
      const userDecision = yield* LoopInterrupt.interrupt({
        reason: "ToolNeedsApproval",
        toolCall: call,
      })
      // userDecision 是 Command.Resume 携带的值
      if (userDecision === "deny") return deniedResult(call)
    }
    return yield* executeTool(call)
  })
```

**收益**：比 v4 `ApprovalStore` 更通用——任意工具可暂停 Loop 等待外部输入（Owner 微信确认、UI 表单、定时器到期）；与 Effect Fiber 天然集成。

---

### #3 Spec 驱动开发四制品（spec-kit）

**spec-kit 做法**：
- SDD 四阶段：Conception → Specification → Implementation → Validation
- 每个变更有独立目录，含 `proposal.md` / `specs/` / `design.md` / `tasks.md` 四个制品
- spec 文档直接驱动 AI 实现，`tasks.md` 用 `1.1 [x] Add theme context` checkbox 标记进度

**Butler v5 现状**：
- `project_todos` 是简单 todo 列表，没有 spec 阶段
- `delegate_task` 接受自由文本指令，AI 容易跑偏

**建议改进**：
在 `packages/domain/src/projects/` 增加 Spec ADT：

```typescript
// packages/domain/src/projects/spec.ts
export type SpecArtifact =
  | { readonly _tag: "Proposal"; readonly content: string; readonly rationale: string }
  | { readonly _tag: "Specs"; readonly sections: readonly SpecSection[] }
  | { readonly _tag: "Design"; readonly decisions: readonly DesignDecision[] }
  | { readonly _tag: "Tasks"; readonly items: readonly TaskItem[] }

export type TaskItem = {
  readonly id: string               // "1.1"
  readonly title: string             // "Add theme context"
  readonly completed: boolean        // [x] / [ ]
  readonly changeType: ChangeType    // 见 #4
  readonly acceptanceCriteria?: readonly string[]
}

// delegate_task 接受 spec 引用，而非自由文本
export const delegateTask = (spec: SpecArtifact, scope: TaskScope) =>
  Effect.gen(function* () {
    // 验证 spec 完整性
    yield* validateSpec(spec)
    // 按 tasks.md 顺序执行
    for (const item of spec.tasks.items) {
      if (!item.completed) {
        yield* executeTaskItem(item)
      }
    }
  })
```

**收益**：spec 是"AI 不跑偏的契约"；变更类型可驱动权限策略（见 #4）；checkbox 状态可作为 ArtifactGraph 推断依据（见 #18）。

---

### #4 变更类型分类（OpenSpec）

**OpenSpec 做法**：
- 每个变更有显式类型：`ADDED` / `REMOVED` / `MODIFIED` / `RENAMED`
- Delta 规范合并机制：变更用 `## ADDED/REMOVED/MODIFIED/RENAMED` 描述
- 不同类型可触发不同审批策略

**Butler v5 现状**：
- Task 只有 `id` / `title` / `completed`，没有变更类型
- 权限策略无法基于"这次是删还是改"做差异化

**建议改进**：
在 `packages/domain/src/workflows/types.ts` 的 Task 加 `changeType`：

```typescript
// packages/domain/src/workflows/types.ts
export type ChangeType = "augment" | "refactor" | "remove" | "fix" | "perf"

export type Task = {
  readonly id: string
  readonly title: string
  readonly changeType: ChangeType
  readonly completed: boolean
}

// packages/domain/src/permissions/policy.ts
// 纯函数：基于变更类型判定权限
export const policyForChange = (task: Task, agent: AgentPersona): Decision =>
  task.changeType === "remove" && agent.role !== "owner"
    ? { _tag: "Deny", reason: "Remove requires owner" }
    : task.changeType === "refactor" && !agent.canRefactor
    ? { _tag: "Ask", reason: "Refactor needs approval" }
    : { _tag: "Allow" }
```

**收益**：`remove` 类变更强制 Owner 审批；`refactor` 默认询问；`fix`/`augment` 放行。比 v4 的 `BUTLER_PROJECT_DELETE_MATURITY_GATE` 更细粒度。

---

## 四、P1 优化建议（强烈推荐）

### #5 工具 Schema 自动转 JSON Schema（OpenCode）

**OpenCode 做法**：
- 工具定义用 `Def<Parameters, M>` 接口，`parameters: Schema.Decoder<unknown>` 是 Effect Schema
- 自动生成 `jsonSchema?: JSONSchema7` 提供给 LLM
- `ExecuteResult<M>` 支持标题/元数据/输出文本/附件

**Butler v5 现状**：
- `ToolCall` / `ToolResult` ADT 已有
- 但没明确"参数 Effect Schema → JSON Schema"的转换层

**建议改进**：
在 `packages/application/src/tools/` 增加 `defineTool` 帮助函数：

```typescript
// packages/application/src/tools/define-tool.ts
import * as S from "@effect/schema/Schema"
import { toJsonSchema } from "@effect/schema/JSONSchema"

export const defineTool = <P extends S.Schema<any, any>>(
  id: string,
  description: string,
  paramsSchema: P,
  execute: (args: S.Schema.Type<P>) => Effect.Effect<ToolResult, ToolError>
): ToolDefinition => ({
  id,
  description,
  parameters: paramsSchema,
  jsonSchema: toJsonSchema(paramsSchema),  // 自动转 JSON Schema
  execute,
})
```

**收益**：开发新工具只需写 Effect Schema，JSON Schema 自动生成；避免手写两份 schema 漂移。

---

### #6 MCP 动态发现 + 工具缓存失效（Cline）

**Cline 做法**：
- MCP Manager 管理多 server 连接，支持传输变更检测
- 工具缓存：连接后 `listTools` 缓存，server 通知时失效重载

**Butler v5 现状**：
- MCP Port 提到了，但没说动态发现/失效策略

**建议改进**：
在 `packages/infrastructure/src/mcp/` 实现完整生命周期：

```typescript
// packages/infrastructure/src/mcp/manager.ts
export const McpManagerLive = Layer.effect(McpManager, Effect.gen(function* () {
  const servers = new Map<string, McpConnection>()

  return McpManager.of({
    connect: (config: McpServerConfig) =>
      Effect.gen(function* () {
        const conn = yield* createConnection(config)
        const tools = yield* conn.listTools()
        servers.set(config.id, { conn, tools, version: 0 })
      }),

    getTools: () => Effect.sync(() =>
      Array.from(servers.values()).flatMap(s => s.tools)
    ),

    // 服务器通知工具变更时，version++ 触发缓存失效
    onToolListChanged: (serverId: string) =>
      Effect.sync(() => {
        const s = servers.get(serverId)
        if (s) s.version++
      }),
  })
}))
```

**收益**：避免每次工具调用都查 server；变更通知驱动自动失效。

---

### #7 Dream 两阶段记忆巩固（nanobot）

**nanobot 做法**：
- Phase 1（短期记忆）：当前会话历史，原子写 + fsync
- Phase 2（长期记忆）：跨会话智能摘要 + 提取，异步跑

**Butler v5 现状**：
- CQRS 读模型投影是单一阶段
- 写入即投影，没有"会话结束后异步巩固"的概念

**建议改进**：
在 `packages/application/src/memory/` 拆分短期/长期：

```typescript
// packages/application/src/memory/store-observation.ts
// Phase 1: 会话中只写短期观察（快）
export const storeShortTerm = (obs: Observation) =>
  Effect.gen(function* () {
    const eventStore = yield* EventStoreService
    // 追加事件，不触发读模型重算
    yield* eventStore.append({ type: "ObservationStored", payload: obs })
  })

// Phase 2: 会话结束后异步巩固（慢）
// 由 outbox-worker 触发
export const consolidate = (sessionId: string) =>
  Effect.gen(function* () {
    const observations = yield* loadSession(sessionId)
    const facts = yield* extractFacts(observations)  // LLM 调用
    yield* storeLongTermFacts(facts)
    yield* updateProjection(facts)
  })
```

**收益**：会话中写入低延迟；巩固任务异步跑不阻塞 Loop；与 Outbox Pattern 天然集成。

---

### #8 双策略压缩（Cline）

**Cline 做法**：
- 基础压缩：规则截断（保留头尾、丢弃中间）
- 代理压缩：LLM 摘要（用专用 compaction agent）
- Token 预算 + 阈值触发

**Butler v5 现状**：
- `Compressing` 状态只有 `reason`，没明确策略
- 压缩触发后默认走 LLM 摘要

**建议改进**：
细化 `CompressReason` 和 `Compressing` 状态：

```typescript
// packages/domain/src/conversation/types.ts
export type CompressReason =
  | { readonly _tag: "BudgetOverflow"; readonly tokens: number; readonly limit: number }
  | { readonly _tag: "TurnLimit"; readonly turns: number; readonly limit: number }
  | { readonly _tag: "Manual" }

export type CompressStrategy = "truncate" | "summarize" | "hybrid"

export type LoopState =
  | ...
  | {
      readonly _tag: "Compressing"
      readonly reason: CompressReason
      readonly strategy: CompressStrategy
      readonly messages: readonly Message[]
      readonly preserveTail: number   // 尾部保护条数
    }
```

策略选择纯函数：
```typescript
// packages/domain/src/conversation/policy.ts
export const chooseStrategy = (reason: CompressReason, budget: TokenBudget): CompressStrategy => {
  // 紧急溢出先 truncate 救急
  if (reason._tag === "BudgetOverflow" && reason.tokens > reason.limit * 1.2)
    return "truncate"
  // 预算充足走 summarize 保信息
  if (budget.remaining > 4000) return "summarize"
  // 中间情况 hybrid
  return "hybrid"
}
```

**收益**：紧急情况快速救场不调 LLM；正常情况保信息；混合策略兼顾。

---

### #9 轻量 EventBus（nanobot）

**nanobot 做法**：
- 全异步消息总线：Channel → MessageBus → AgentLoop → AgentRunner → Channel
- 解耦聊天平台延迟与 Agent 执行

**Butler v5 现状**：
- `apps/gateway/inbound.ts` 直接调 `application/` 层
- iLink 延迟会阻塞 Loop

**建议改进**：
网关层引入 Effect Stream 作为 EventBus：

```typescript
// apps/gateway/src/inbound.ts
import { Stream, Queue } from "effect"

export const startGateway = Effect.gen(function* () {
  const inboundQueue = yield* Queue.unbounded<InboundMessage>()

  // iLink webhook → 入队（快）
  const hono = new Hono()
  hono.post("/wechat", (c) => c.req.json().then(msg =>
    Effect.runPromise(Queue.offer(inboundQueue, msg))
  ))

  // 后台消费者（慢）
  yield* Effect.fork(
    Stream.fromQueue(inboundQueue).pipe(
      Stream.run(msg => runAgentLoop(msg))
    )
  )
})
```

**收益**：网关 P99 延迟降到 ms 级；Loop 慢不影响接收；天然背压（Queue 满时阻塞生产者）。

---

## 五、P2 优化建议（推荐实施）

### #10 AgentPersona 三元组（crewAI）

**crewAI 做法**：每个 Agent 有 `Role` + `Goal` + `Backstory`，驱动 system prompt 生成。

**Butler v5 现状**：`AgentConfig` 没有显式 persona 概念。

**建议改进**：
```typescript
// packages/domain/src/conversation/persona.ts
export type AgentPersona = {
  readonly role: string         // "代码审查员"
  readonly goal: string         // "保证代码质量"
  readonly backstory: string   // "你是资深工程师..."
  readonly tools: readonly string[]  // 允许的工具 id
  readonly canRefactor: boolean
}

// 编译期约束：role/goal 不能空
export const makePersona = (p: AgentPersona): AgentPersona => {
  if (!p.role || !p.goal) throw new Error("persona incomplete")
  return p
}
```

**收益**：编译期保证 persona 完整；运行时映射到 system prompt 段落；权限策略可读 persona 字段。

---

### #11 Send API 并行委派（LangGraph）

**LangGraph 做法**：节点返回 `[Send("node", payload)]` 动态分发，多子图实例并行执行。

**Butler v5 现状**：`delegate_task` 串行。

**建议改进**：
```typescript
// packages/application/src/workflows/dispatch-parallel.ts
export const dispatchParallel = (tasks: readonly TaskSpec[]) =>
  Effect.gen(function* () {
    const fibers = yield* Effect.all(
      tasks.map(t => Effect.fork(runTask(t))),
      { concurrency: "unbounded" }
    )
    const results = yield* Effect.all(fibers.map(Fiber.join))
    // 用 Channel reducer 聚合（依赖 #1）
    return aggregateResults(results)
  })
```

**收益**：N 个独立子任务耗时 = max 而非 sum；与 #1 Channel reducer 配合自动合并结果。

---

### #12 DeltaChannel 增量检查点（LangGraph）

**LangGraph 做法**：仅存增量更新，`snapshot_frequency` 控制全量快照频率，避免长会话回放慢。

**Butler v5 现状**：每次事件全量持久化。

**建议改进**：
```typescript
// packages/infrastructure/src/eventstore/hybrid-store.ts
export const HybridEventStore = Layer.effect(EventStoreService, Effect.gen(function* () {
  let eventCount = 0
  const SNAPSHOT_EVERY = 100  // 每 100 事件一个 snapshot

  return EventStoreService.of({
    append: (event) => Effect.gen(function* () {
      yield* appendEvent(event)
      eventCount++
      if (eventCount % SNAPSHOT_EVERY === 0) {
        const state = yield* rehydrate()  // 从事件重放
        yield* saveSnapshot(state)
      }
    }),

    load: (id) => Effect.gen(function* () {
      const snapshot = yield* loadLatestSnapshot(id)
      const events = yield* loadEventsAfter(snapshot.version)
      return applyEvents(snapshot.state, events)
    }),
  })
}))
```

**收益**：长会话加载从 O(N 事件) 降到 O(snapshot + Δ)。

---

### #13 RelativeIndenter + 多策略 patch（aider）

**aider 做法**：
- `RelativeIndenter`：用相对缩进解决 LLM 输出与真实代码缩进不一致
- `flexible_search_and_replace`：多策略回退（cherry-pick → diff-match-patch → 正则）

**Butler v5 现状**：dev_engine 编辑策略没明确。

**建议改进**：
```typescript
// packages/infrastructure/src/edit/apply-patch.ts
export const applyPatch = (original: string, patch: Patch) =>
  Effect.gen(function* () {
    // 策略 1: 精确匹配
    const r1 = tryExactMatch(original, patch)
    if (r1._tag === "Right") return r1.right

    // 策略 2: RelativeIndenter 归一化
    const r2 = tryRelativeIndent(original, patch)
    if (r2._tag === "Right") return r2.right

    // 策略 3: diff-match-patch 模糊
    const r3 = yield* tryDiffMatchPatch(original, patch)
    if (r3._tag === "Right") return r3.right

    return yield* Effect.fail(new PatchApplyError(...))
  })
```

**收益**：LLM 生成的不精确 patch 也能应用；失败时清晰降级而非报错。

---

### #14 PageRank repo-map（aider）

**aider 做法**：用 PageRank 给代码库节点按重要性排序，树形语法分析 + 引用关系加权。

**Butler v5 现状**：dev_engine 没有代码库摘要能力。

**建议改进**：
```typescript
// packages/application/src/dev-engine/build-repo-map.ts
export const buildRepoMap = (rootDir: string) =>
  Effect.gen(function* () {
    const files = yield* scanSourceFiles(rootDir)
    const symbols = yield* extractSymbols(files)  // 用 TS compiler API
    const graph = buildReferenceGraph(symbols)
    const ranked = pageRank(graph)  // 按重要性排序
    return formatRepoMap(ranked.slice(0, 200))  // Top 200 符号
  })
```

**收益**：LLM 快速理解代码库结构；比纯 grep 更智能；上下文预算更省。

---

### #15 工具自动发现（nanobot）

**nanobot 做法**：`pkgutil.walk_packages` + Entry Point 自动发现，无需手动注册。

**Butler v5 现状**：`ToolRegistry` 手动注册。

**建议改进**：
用 Bun 原生 glob import + 命名约定：

```typescript
// packages/application/src/tools/auto-discover.ts
// Bun 支持 import.meta.glob
const modules = import.meta.glob("./definitions/*.tool.ts", { eager: true })

export const autoDiscoverTools = (): ToolDefinition[] =>
  Object.values(modules)
    .map((m: any) => m.default)
    .filter((t): t is ToolDefinition => t?.id != null)
```

工具文件约定 `*.tool.ts`，每个 `export default defineTool(...)`。

**收益**：新增工具只加文件不改 registry；约定优于配置。

---

## 六、P3 优化建议（可后置）

### #16 ContextGraph 有向图（Gemini-CLI）

**Gemini-CLI 做法**：上下文用有向图管理，可审计可追溯。

**Butler v5 现状**：上下文是线性 `Message[]` 数组。

**建议改进**：
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

---

### #17 Effect.withSpan 自动埋点（LangGraph/LangSmith）

**LangGraph 做法**：每个节点执行自动生成 trace span，含输入/输出/耗时/错误。

**Butler v5 现状**：`infrastructure/observability/tracing.ts` 提到但没设计 API。

**建议改进**：
利用 Effect 内置 tracing，无需自建：

```typescript
// packages/application/src/conversation/run-loop.ts
export const runLoop = (input: UserInput) =>
  Effect.gen(function* () {
    yield* Effect.withSpan("prepare-context")  // 自动埋点
    const ctx = yield* prepareContext(input)
    const resp = yield* Effect.withSpan("call-llm", { attributes: { model: ctx.model } })(
      callLlm(ctx)
    )
    // ...
  }).pipe(
    Effect.withSpan("run-loop", { attributes: { sessionId: input.sessionId } })
  )
```

自定义业务事件用 `Effect.logAnnotated`：
```typescript
yield* Effect.logAnnotated("tool executed", {
  toolId: call.id,
  duration: elapsed,
  success: true,
})
```

**收益**：零成本接入 OpenTelemetry；业务事件结构化；比自建 logger 强。

---

### #18 ArtifactGraph 文件存在性推断（OpenSpec）

**OpenSpec 做法**：用文件存在性推断流程状态（Kahn 拓扑排序），不用显式状态机。

**Butler v5 现状**：workflow 显式状态机管理。

**建议改进**：
保留显式状态机，但增加"文件存在性校验"作为状态恢复兜底：

```typescript
// packages/application/src/workflows/infer-progress.ts
export const inferProgressFromArtifacts = (spec: SpecArtifact): InferredProgress =>
  Effect.gen(function* () {
    const checks = spec.tasks.items.map(item =>
      Effect.map(checkArtifactExists(item.id), exists => ({ item, exists }))
    )
    const results = yield* Effect.all(checks)
    return {
      completed: results.filter(r => r.exists).map(r => r.item.id),
      pending: results.filter(r => !r.exists).map(r => r.item.id),
    }
  })
```

**收益**：状态机损坏时可从文件恢复；Spec SDD（#3）天然有 artifact 文件，配合良好。

---

## 七、优先级路线图

### Phase 1（Week 1-4，与 v5 主文档 Phase 1 同步）
- **P0 #3 Spec SDD 四制品**：在 `domain/projects/` 落地 Spec ADT
- **P0 #4 变更类型分类**：在 `domain/workflows/types.ts` 加 `changeType`
- **P0 #1 Channel 抽象**：在 `domain/workflows/channel.ts` 落地
- **P0 #2 interrupt/resume**：在 `contracts/services/loop.ts` 加 `LoopInterrupt` Tag

### Phase 2（Week 5-8）
- **P1 #5 工具 Schema 自动生成**：`application/tools/define-tool.ts`
- **P1 #7 Dream 两阶段记忆**：`application/memory/store-observation.ts` + `consolidate.ts`
- **P1 #8 双策略压缩**：细化 `CompressReason` / `CompressStrategy`
- **P1 #9 EventBus**：`apps/gateway/inbound.ts` 改造

### Phase 3（Week 9-12）
- **P1 #6 MCP 动态发现**：`infrastructure/mcp/manager.ts`
- **P2 #10 AgentPersona**：`domain/conversation/persona.ts`
- **P2 #11 Send API 并行委派**：`application/workflows/dispatch-parallel.ts`
- **P2 #12 DeltaChannel**：`infrastructure/eventstore/hybrid-store.ts`

### Phase 4（Week 13-16）
- **P2 #13 RelativeIndenter**：`infrastructure/edit/apply-patch.ts`
- **P2 #14 PageRank repo-map**：`application/dev-engine/build-repo-map.ts`
- **P2 #15 工具自动发现**：`application/tools/auto-discover.ts`
- **P3 #16/#17/#18**：可观测性、ContextGraph、ArtifactGraph

---

## 八、与 v5 主文档的章节映射

| 本文档建议 | v5 主文档章节 | 操作 |
|----------|-------------|------|
| #1 Channel 抽象 | §四 工作流域 | 在 `domain/workflows/` 新增 `channel.ts` |
| #2 interrupt/resume | §五 端口与服务 | 在 `contracts/services/` 新增 `loop.ts` 增强 |
| #3 Spec SDD | §四 项目域 | 在 `domain/projects/` 新增 `spec.ts` |
| #4 变更类型 | §四 工作流域 | 修改 `workflows/types.ts` 的 Task |
| #5 工具 Schema | §五 工具 Port | 在 `application/tools/` 新增 `define-tool.ts` |
| #6 MCP 动态发现 | §七 基础设施 | 在 `infrastructure/mcp/` 新增 `manager.ts` |
| #7 Dream 两阶段 | §四 记忆域 | 拆 `application/memory/` 为短/长两模块 |
| #8 双策略压缩 | §四 对话域 | 修改 `conversation/types.ts` 的 Compressing |
| #9 EventBus | §九 网关层 | 修改 `apps/gateway/inbound.ts` |
| #10 AgentPersona | §四 对话域 | 新增 `conversation/persona.ts` |
| #11 Send API | §六 应用层 | 新增 `workflows/dispatch-parallel.ts` |
| #12 DeltaChannel | §七 事件存储 | 新增 `eventstore/hybrid-store.ts` |
| #13 RelativeIndenter | §七 dev_engine | 新增 `infrastructure/edit/apply-patch.ts` |
| #14 PageRank repo-map | §六 dev-engine 用例 | 新增 `dev-engine/build-repo-map.ts` |
| #15 工具自动发现 | §五 工具 Port | 新增 `tools/auto-discover.ts` |
| #16 ContextGraph | §四 对话域 | 新增 `conversation/context-graph.ts` |
| #17 tracing | §七 可观测性 | 在 `infrastructure/observability/tracing.ts` 增强 |
| #18 ArtifactGraph | §六 工作用例 | 新增 `workflows/infer-progress.ts` |

---

## 九、不采纳的设计（明确排除）

避免在后续实施中走回头路：

| 设计 | 来源 | 不采纳原因 |
|------|------|-----------|
| Scala + ZIO | ZIO 生态 | v5 主文档已决定 TS + Effect-TS，不引入第二语言 |
| 全量 Event Sourcing（无 snapshot） | 理论纯度 | 长会话回放慢；用 #12 Hybrid Store |
| WASM 沙箱 | 强隔离 | 部署复杂；dev_engine 用进程级隔离即可 |
| Python 子进程网关 | v4 兼容 | v5 完全重写，不需要兼容 v4 网关 |
| 类继承体系 | OOP 习惯 | 与 FC/IS 冲突；用 Effect Layer + 函数组合 |
| 隐式异常（throw） | JS 习惯 | 违反"错误是值"原则；用 `Effect.fail` + ADT |

---

## 十、验证标准

每条优化建议落地后，需满足：

| 类型 | 验证标准 |
|------|---------|
| **纯函数**（#1/#4/#8/#10） | 单元测试零 mock；代数定律（associativity/identity）成立 |
| **Effect Layer**（#2/#5/#6/#7/#9） | Mock Layer 可替换；运行时 Layer 组合通过 |
| **基础设施**（#12/#13） | 集成测试用真实 DB/文件系统；性能基准达标 |
| **流程类**（#3/#11/#15） | 端到端测试覆盖完整流程；失败可回滚 |
| **可观测性**（#16/#17/#18） | trace 可在 Jaeger 看到；artifact 状态可恢复 |

---

## 十一、参考文档

### 外部项目解析（来源）
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

### Butler v5 主文档（被优化对象）
- [butler-v5-functional-architecture-2026-07-30.md](butler-v5-functional-architecture-2026-07-30.md) — 主方案
- [functional-architecture-migration-plan-2026-07-30.md](functional-architecture-migration-plan-2026-07-30.md) — 迁移主方案
- [strangler-fig-migration-guide-2026-07-30.md](strangler-fig-migration-guide-2026-07-30.md) — 绞杀者模式指南
- [functional-migration-supplement-2026-07-30.md](functional-migration-supplement-2026-07-30.md) — 数据迁移补充

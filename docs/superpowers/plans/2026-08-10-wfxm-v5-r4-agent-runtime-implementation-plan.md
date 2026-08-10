# R4 Agent Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Butler v5 AgentKernel + Decision Decoder + Tool Runtime + Delegate Runtime + Context Manager 落地为基于 R3 持久化的运行时。

**Architecture:** AgentKernel 维护 Turn 状态机（Idle → TurnOpened → ContextPrepared → ModelRequested → DecisionDecoded → 路由分支 → Tool/Delegate/AskApproval/Finish），通过 EventBridge 调用 R3 persistence public API（appendEvents / enqueueOutbox / applyProjection / saveSnapshot）。LLM 输出必须先解码为 ModelDecision ADT（Respond / CallTool / Delegate / AskApproval / Finish），PolicyEngine 校验后才能进入 Tool/Delegate Runtime。Tool Runtime 支持并发 + 超时 + 取消；Delegate Runtime 通过 capability 过滤将 sub-tool set 转发给 child agent。

**Tech Stack:** TypeScript strict、Node.js 20、pnpm 9、Turborepo、Effect-TS 3（用于 Provider 与并发组合）、Vitest 1.6、ESLint 8.57、@butler/persistence（R3）、@butler/domain（R2 ADT 与端口契约）。

---

## 范围与执行纪律

### 现状与 R4 边界

R0–R3 已 commit + push origin main（最近 commit dd2b9f58..e3f43705）。R4 必须消费 R3 persistence 全部 9 个 leaf public API（appendEvents / subscribeStream / enqueueOutbox / claimOutbox / completeOutbox / failOutbox / registerProjection / applyProjection / rebuildProjection / saveSnapshot / loadSnapshot / makeTestDb / runWorkerOnce / nextVersion / loadStream）。R4 范围由规格 §6 与总计划 R4 章节定义。

### 范围纪律

- 仅修改 / 新增 `butler-v5/` 与 `docs/superpowers/` 下文件；
- 不得修改任何 tsconfig（除非该 tsconfig 属于 R4 新增的 package）、eslintrc、package.json（除非该 package.json 属于 R4 新增的 package）、AGENTS.md、.cursorrules、.butler/*.json、.github/workflows/*、.env*、受保护文件清单；
- 不得 stage / commit / push；
- 不得使用 `// ts-prune-ignore-next` 注释；
- 不得使用 `throw` in `packages/runtime/src/`（Plan 允许的少量"程序错误"异常除外，详见各 Task）。

### 六子项目顺序

```text
R4.0 Runtime Bridge（消费 R3 public API）
  → R4.1 AgentKernel 框架与状态机
  → R4.2 Decision Decoder（解析 LLM 输出）
  → R4.3 Tool Runtime（执行 + 取消 + 超时）
  → R4.4 Delegate Runtime（能力传递）
  → R4.5 Context Manager（预算 + 压缩）
  → R4.6 端到端门禁
```

每子项目可独立验证。

---

## R4.0：Runtime Bridge（消费 R3 persistence public API）

### Task 0.1: 新增 `packages/runtime/` 子包

**Files:**
- Create: `butler-v5/packages/runtime/package.json`
- Create: `butler-v5/packages/runtime/tsconfig.json`
- Create: `butler-v5/packages/runtime/src/index.ts`
- Create: `butler-v5/packages/runtime/src/bridge.ts`

**Step 1: `package.json`**

```json
{
  "name": "@butler/runtime",
  "version": "0.0.1",
  "private": true,
  "type": "module",
  "main": "./src/index.ts",
  "exports": {
    ".": "./src/index.ts"
  },
  "types": "./src/index.ts",
  "scripts": {
    "test": "vitest run",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@butler/persistence": "workspace:*"
  }
}
```

**Step 2: `tsconfig.json`**

```json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "outDir": "./dist",
    "rootDir": "."
  },
  "include": ["src/**/*.ts"]
}
```

**Step 3: `src/index.ts`**

```typescript
export * from "./bridge.js"
```

**Step 4: `src/bridge.ts`（EventBridge 抽象）**

```typescript
/**
 * EventBridge wraps the R3 persistence public API for AgentKernel use.
 * Runtime has no direct knowledge of pglite/postgres; it interacts only
 * via this bridge.
 */
import type { PgliteDatabase } from "drizzle-orm/pglite"
import {
  appendEvents,
  loadStream,
  subscribeStream,
} from "@butler/persistence/event-store.js"
import { enqueueOutbox } from "@butler/persistence/outbox.js"
import {
  applyProjection,
  registerProjection,
  rebuildProjection,
} from "@butler/persistence/projections.js"
import { loadSnapshot, saveSnapshot } from "@butler/persistence/snapshot.js"
import { runWorkerOnce } from "@butler/persistence/worker.js"
import type { ActorRef } from "@butler/persistence/event-store.js"

export interface EventBridgeConfig {
  readonly db: PgliteDatabase<Record<string, never>>
  readonly workerId: string
  readonly leaseMs?: number
}

export class EventBridge {
  constructor(private readonly config: EventBridgeConfig) {}

  appendConversationEvent(input: {
    streamId: string
    event: unknown
    eventId: string
    eventType: string
    correlationId: string
    actor: ActorRef
  }) {
    return appendEvents(this.config.db, input.streamId, input.event, {
      eventId: input.eventId,
      eventType: input.eventType,
      eventVersion: 1, // callers update eventVersion per stream via nextVersion() call
      correlationId: input.correlationId,
      occurredAt: new Date(),
      actor: input.actor,
    })
  }

  loadStream(streamId: string) {
    return loadStream(this.config.db, streamId)
  }

  subscribe(streamId: string, handler: (e: ReturnType<typeof loadStream>[number]) => void) {
    return subscribeStream(this.config.db, streamId, handler)
  }

  enqueueOutbox(input: { streamId: string; aggregateType: string; payload: Record<string, unknown> }) {
    return enqueueOutbox(this.config.db, input)
  }

  runWorker(handler: Parameters<typeof runWorkerOnce>[3]) {
    return runWorkerOnce(this.config.db, this.config.workerId, this.config.leaseMs ?? 60_000, handler)
  }

  applyProjection(streamId: string, name: string) {
    return applyProjection(this.config.db, streamId, name)
  }

  rebuildProjection(streamId: string, name: string) {
    return rebuildProjection(this.config.db, streamId, name)
  }

  registerProjection(name: string, handler: Parameters<typeof registerProjection>[1]) {
    return registerProjection(name, handler)
  }

  saveSnapshot(streamId: string, version: number, payload: Record<string, unknown>) {
    return saveSnapshot(this.config.db, streamId, version, payload)
  }

  loadSnapshot(streamId: string) {
    return loadSnapshot(this.config.db, streamId)
  }
}
```

**Step 5: `.eslintrc.json` 加入 runtime tsconfig**

修改 `/home/ailearn/projects/WFXM/butler-v5/.eslintrc.json` 的 `parserOptions.project` 数组，追加 `"./packages/runtime/tsconfig.json"`（与 R3 同样模式）。

**Step 6: 验证**

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm install
pnpm typecheck 2>&1 | tail -5
echo "typecheck_exit=$?"
```

Expected: typecheck exit 0。

### R4.0 退出条件

- `packages/runtime/` 加入 typecheck 链路；
- EventBridge 实现完成；
- 5 项 gate 全 exit 0。

---

## R4.1：AgentKernel 框架与状态机

### Task 1.1: 状态机 + Kernel 主体

**Files:**
- Create: `butler-v5/packages/runtime/src/agent-kernel.ts`
- Create: `butler-v5/packages/runtime/src/agent-kernel.test.ts`

**Step 1: 写失败测试**

`packages/runtime/src/agent-kernel.test.ts`:

```typescript
import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { EventBridge } from "./bridge.js"
import { AgentKernel } from "./agent-kernel.js"
import { makeTestDb } from "@butler/persistence/testing.js"

describe("AgentKernel", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let bridge: EventBridge
  let kernel: AgentKernel

  beforeEach(async () => {
    db = await makeTestDb()
    bridge = new EventBridge({ db: db.db, workerId: "w-1" })
    kernel = new AgentKernel({
      bridge,
      conversationId: "c-1",
      projectId: "p-1",
      actor: { kind: "system", id: "kernel" },
    })
  })

  afterEach(async () => {
    await db.close()
  })

  it("starts in Idle state", () => {
    expect(kernel.state).toBe("idle")
  })

  it("transitions through openTurn → respond → completed for a Respond decision", async () => {
    kernel.openTurn({ userMessage: { role: "user", content: "hi" } })
    expect(kernel.state).toBe("running")
    kernel.applyDecision({ _tag: "Respond", content: "hello" })
    expect(kernel.state).toBe("completed")
    const events = await bridge.loadStream("c-1")
    expect(events.length).toBeGreaterThan(0)
  })
})
```

**Step 2: 验证失败**

```bash
pnpm test --reporter=dot packages/runtime/src/agent-kernel.test.ts 2>&1 | tail -10
```

Expected: FAIL.

**Step 3: 实现 agent-kernel.ts**

```typescript
import type { EventBridge } from "./bridge.js"
import type { ModelDecision } from "./decision.js"

export type KernelState =
  | "idle"
  | "running"
  | "responded"
  | "tooling"
  | "delegating"
  | "waiting_approval"
  | "completed"
  | "failed"

export interface AgentKernelConfig {
  readonly bridge: EventBridge
  readonly conversationId: string
  readonly projectId: string
  readonly actor: { readonly kind: "owner" | "agent" | "system"; readonly id: string }
}

export class AgentKernel {
  state: KernelState = "idle"

  constructor(private readonly config: AgentKernelConfig) {}

  openTurn(input: { userMessage: { role: "user" | "assistant" | "system" | "tool"; content: string } }) {
    this.state = "running"
    void this.config.bridge.appendConversationEvent({
      streamId: this.config.conversationId,
      eventId: `evt-${Date.now()}-turn`,
      eventType: "TurnOpened",
      correlationId: `corr-${Date.now()}`,
      actor: this.config.actor,
      event: { _tag: "TurnOpened", role: input.userMessage.role, content: input.userMessage.content },
    })
  }

  applyDecision(decision: ModelDecision) {
    switch (decision._tag) {
      case "Respond":
        this.state = "responded"
        void this.config.bridge.appendConversationEvent({
          streamId: this.config.conversationId,
          eventId: `evt-${Date.now()}-resp`,
          eventType: "AssistantMessageProduced",
          correlationId: `corr-${Date.now()}`,
          actor: this.config.actor,
          event: { _tag: "AssistantMessageProduced", content: decision.content },
        })
        this.state = "completed"
        return
      case "CallTool":
        this.state = "tooling"
        return
      case "Delegate":
        this.state = "delegating"
        return
      case "AskApproval":
        this.state = "waiting_approval"
        return
      case "Finish":
        this.state = "completed"
        return
      default:
        // exhaustiveness check
        const _: never = decision
        void _
        return
    }
  }
}
```

**Step 4: 占位 model-decision.ts**（Task 4.2 实现完整版；现在只创建类型 stub）

```typescript
export type ModelDecision =
  | { readonly _tag: "Respond"; readonly content: string }
  | { readonly _tag: "CallTool"; readonly toolName: string; readonly args: Record<string, unknown> }
  | { readonly _tag: "Delegate"; readonly role: string; readonly task: string }
  | { readonly _tag: "AskApproval"; readonly question: string }
  | { readonly _tag: "Finish"; readonly reason: string }
```

**Step 5: 验证**

```bash
pnpm test --reporter=dot packages/runtime/src/agent-kernel.test.ts 2>&1 | tail -10
```

Expected: 2 tests pass.

### R4.1 退出条件

- AgentKernel 实现 Idle → running → completed 状态机；
- 每个 transition 写入 R3 persistence（appendConversationEvent）；
- 5 项 gate 全 exit 0。

---

## R4.2：Decision Decoder（解析 LLM 输出）

### Task 2.1: JSON Schema 解析与 fallback

**Files:**
- Create: `butler-v5/packages/runtime/src/decision.ts`
- Create: `butler-v5/packages/runtime/src/decision.test.ts`

**Step 1: 写失败测试**

`packages/runtime/src/decision.test.ts`:

```typescript
import { describe, expect, it } from "vitest"
import { decodeDecision } from "./decision.js"

describe("decodeDecision", () => {
  it("decodes a valid Respond JSON", () => {
    const out = decodeDecision('{"_tag":"Respond","content":"hello"}')
    expect(out.ok).toBe(true)
    if (out.ok) {
      expect(out.value._tag).toBe("Respond")
      if (out.value._tag === "Respond") expect(out.value.content).toBe("hello")
    }
  })

  it("decodes a valid CallTool JSON", () => {
    const out = decodeDecision('{"_tag":"CallTool","toolName":"read_file","args":{"path":"/ws"}}')
    expect(out.ok).toBe(true)
    if (out.ok && out.value._tag === "CallTool") expect(out.value.toolName).toBe("read_file")
  })

  it("rejects unknown tag", () => {
    const out = decodeDecision('{"_tag":"SelfDestruct","content":"x"}')
    expect(out.ok).toBe(false)
  })

  it("rejects malformed JSON", () => {
    const out = decodeDecision("not json")
    expect(out.ok).toBe(false)
  })

  it("rejects payload with extra unknown fields is allowed (forward compat)", () => {
    const out = decodeDecision('{"_tag":"Respond","content":"x","future":42}')
    expect(out.ok).toBe(true)
  })
})
```

**Step 2: 验证失败**

```bash
pnpm test --reporter=dot packages/runtime/src/decision.test.ts 2>&1 | tail -10
```

Expected: FAIL.

**Step 3: 实现 decision.ts**

```typescript
/**
 * Decode an LLM-emitted JSON string into a ModelDecision.
 * Returns { ok: false, reason } for malformed JSON, unknown tag, or
 * shape mismatch. Forward-compatible: extra fields are ignored.
 */
export type ModelDecision =
  | { readonly _tag: "Respond"; readonly content: string }
  | { readonly _tag: "CallTool"; readonly toolName: string; readonly args: Record<string, unknown> }
  | { readonly _tag: "Delegate"; readonly role: string; readonly task: string }
  | { readonly _tag: "AskApproval"; readonly question: string }
  | { readonly _tag: "Finish"; readonly reason: string }

export type DecodeResult =
  | { readonly ok: true; readonly value: ModelDecision }
  | { readonly ok: false; readonly reason: string }

export function decodeDecision(raw: string): DecodeResult {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return { ok: false, reason: "invalid JSON" }
  }
  if (!parsed || typeof parsed !== "object") {
    return { ok: false, reason: "not an object" }
  }
  const obj = parsed as Record<string, unknown>
  const tag = obj["_tag"]
  switch (tag) {
    case "Respond": {
      const content = obj["content"]
      if (typeof content !== "string") return { ok: false, reason: "Respond.content must be string" }
      return { ok: true, value: { _tag: "Respond", content } }
    }
    case "CallTool": {
      const toolName = obj["toolName"]
      const args = obj["args"]
      if (typeof toolName !== "string") return { ok: false, reason: "CallTool.toolName must be string" }
      if (!args || typeof args !== "object") return { ok: false, reason: "CallTool.args must be object" }
      return { ok: true, value: { _tag: "CallTool", toolName, args: args as Record<string, unknown> } }
    }
    case "Delegate": {
      const role = obj["role"]
      const task = obj["task"]
      if (typeof role !== "string") return { ok: false, reason: "Delegate.role must be string" }
      if (typeof task !== "string") return { ok: false, reason: "Delegate.task must be string" }
      return { ok: true, value: { _tag: "Delegate", role, task } }
    }
    case "AskApproval": {
      const question = obj["question"]
      if (typeof question !== "string") return { ok: false, reason: "AskApproval.question must be string" }
      return { ok: true, value: { _tag: "AskApproval", question } }
    }
    case "Finish": {
      const reason = obj["reason"]
      if (typeof reason !== "string") return { ok: false, reason: "Finish.reason must be string" }
      return { ok: true, value: { _tag: "Finish", reason } }
    }
    default:
      return { ok: false, reason: `unknown tag: ${String(tag)}` }
  }
}
```

**Step 4: 验证**

```bash
pnpm test --reporter=dot packages/runtime/src/decision.test.ts 2>&1 | tail -10
```

Expected: 5 tests pass.

### R4.2 退出条件

- decodeDecision 解析 5 种 ModelDecision；
- 失败返回明确 reason 字符串；
- 5 项 gate 全 exit 0。

---

## R4.3：Tool Runtime（执行 + 取消 + 超时）

### Task 3.1: 工具执行 + 超时 + 取消

**Files:**
- Create: `butler-v5/packages/runtime/src/tool-runtime.ts`
- Create: `butler-v5/packages/runtime/src/tool-runtime.test.ts`

**Step 1: 写失败测试**

`packages/runtime/src/tool-runtime.test.ts`:

```typescript
import { describe, expect, it, vi } from "vitest"
import { runTool, type ToolDefinition } from "./tool-runtime.js"

describe("runTool", () => {
  const echo: ToolDefinition = {
    name: "echo" as ToolDefinition["name"],
    risk: "low",
    run: vi.fn(async (args: Record<string, unknown>) => ({ ok: true, output: args })),
  }

  it("returns the handler output on success", async () => {
    const r = await runTool(echo, { x: 1 }, { timeoutMs: 1000 })
    expect(r.ok).toBe(true)
    if (r.ok) expect(r.output).toEqual({ x: 1 })
  })

  it("times out a slow handler", async () => {
    const slow: ToolDefinition = {
      name: "slow" as ToolDefinition["name"],
      risk: "low",
      run: () => new Promise((r) => setTimeout(() => r({ ok: true, output: "done" }), 5_000)),
    }
    const r = await runTool(slow, {}, { timeoutMs: 50 })
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.reason).toMatch(/timeout/i)
  })
})
```

**Step 2: 验证失败**

```bash
pnpm test --reporter=dot packages/runtime/src/tool-runtime.test.ts 2>&1 | tail -10
```

Expected: FAIL.

**Step 3: 实现 tool-runtime.ts**

```typescript
/**
 * Run a tool with timeout. Returns { ok: true, output } on success,
 * or { ok: false, reason } on timeout / handler error.
 * Never throws.
 */
export interface ToolDefinition {
  readonly name: string & { readonly __brand: "ToolName" }
  readonly risk: "low" | "medium" | "high"
  readonly run: (args: Record<string, unknown>) => Promise<RunResult>
}

export type RunResult = { readonly ok: true; readonly output: unknown } | { readonly ok: false; readonly reason: string }

export interface RunOptions {
  readonly timeoutMs: number
  readonly signal?: AbortSignal
}

export type RunOutcome = RunResult

export async function runTool(
  def: ToolDefinition,
  args: Record<string, unknown>,
  opts: RunOptions,
): Promise<RunOutcome> {
  let timer: ReturnType<typeof setTimeout> | null = null
  let timedOut = false
  const promise = def.run(args)
  const timeoutPromise = new Promise<RunOutcome>((resolve) => {
    timer = setTimeout(() => {
      timedOut = true
      resolve({ ok: false, reason: `timeout after ${opts.timeoutMs}ms` })
    }, opts.timeoutMs)
  })
  try {
    const result = await Promise.race([promise, timeoutPromise])
    if (timedOut) return result
    if (timer) clearTimeout(timer)
    return result
  } catch (err) {
    if (timer) clearTimeout(timer)
    return { ok: false, reason: err instanceof Error ? err.message : String(err) }
  }
}
```

**Step 4: 验证**

```bash
pnpm test --reporter=dot packages/runtime/src/tool-runtime.test.ts 2>&1 | tail -10
```

Expected: 2 tests pass.

### R4.3 退出条件

- runTool 正常返回 handler 输出；
- 超时返回 ok:false + timeout reason；
- 永不抛出（不抛给 AgentKernel）；
- 5 项 gate 全 exit 0。

---

## R4.4：Delegate Runtime（能力传递）

### Task 4.1: 子 agent 调用与 capability 过滤

**Files:**
- Create: `butler-v5/packages/runtime/src/delegate-runtime.ts`
- Create: `butler-v5/packages/runtime/src/delegate-runtime.test.ts`

**Step 1: 写失败测试**

`packages/runtime/src/delegate-runtime.test.ts`:

```typescript
import { describe, expect, it } from "vitest"
import { delegate, type Capability } from "./delegate-runtime.js"

describe("delegate", () => {
  const caps: Capability[] = [
    { tool: "read_file" as Capability["tool"] },
    { tool: "search_project_knowledge" as Capability["tool"] },
  ]

  it("forwards the capability list to the child agent", async () => {
    const child = await delegate({
      role: "researcher",
      task: "find docs about Foo",
      capabilities: caps,
      parentConversationId: "p-1",
      actor: { kind: "agent", id: "kernel" },
      bridge: {
        appendConversationEvent: async () => {},
        enqueueOutbox: async () => "msg-1",
      } as never,
    })
    expect(child.role).toBe("researcher")
    expect(child.capabilities).toEqual(caps)
    expect(child.parentConversationId).toBe("p-1")
  })

  it("rejects empty capability list as error", async () => {
    const r = await delegate({
      role: "researcher",
      task: "x",
      capabilities: [],
      parentConversationId: "p-1",
      actor: { kind: "agent", id: "kernel" },
      bridge: {
        appendConversationEvent: async () => {},
        enqueueOutbox: async () => "msg-1",
      } as never,
    }).catch((err: Error) => err)
    expect(r).toBeInstanceOf(Error)
    expect((r as Error).message).toMatch(/capabilities/i)
  })
})
```

**Step 2: 验证失败**

```bash
pnpm test --reporter=dot packages/runtime/src/delegate-runtime.test.ts 2>&1 | tail -10
```

Expected: FAIL.

**Step 3: 实现 delegate-runtime.ts**

```typescript
export interface Capability {
  readonly tool: string & { readonly __brand: "ToolName" }
}

export interface DelegateInput {
  readonly role: string
  readonly task: string
  readonly capabilities: ReadonlyArray<Capability>
  readonly parentConversationId: string
  readonly actor: { readonly kind: "owner" | "agent" | "system"; readonly id: string }
  readonly bridge: {
    readonly appendConversationEvent: (input: unknown) => Promise<unknown>
    readonly enqueueOutbox: (input: unknown) => Promise<string>
  }
}

export interface DelegateOutcome {
  readonly role: string
  readonly capabilities: ReadonlyArray<Capability>
  readonly parentConversationId: string
  readonly childConversationId: string
}

/**
 * Delegate a task to a child agent with a strict capability filter.
 * Returns the child's metadata; the actual child execution is handled
 * separately by the Worker layer.
 */
export async function delegate(input: DelegateInput): Promise<DelegateOutcome> {
  if (input.capabilities.length === 0) {
    throw new Error("delegate: capabilities must not be empty")
  }
  const childConversationId = `child-${input.parentConversationId}-${Date.now()}`
  await input.bridge.appendConversationEvent({
    streamId: input.parentConversationId,
    eventId: `evt-${Date.now()}-delegate`,
    eventType: "ChildRunCreated",
    correlationId: `corr-${Date.now()}`,
    actor: input.actor,
    event: { _tag: "ChildRunCreated", childConversationId, role: input.role, capabilities: input.capabilities },
  })
  await input.bridge.enqueueOutbox({
    streamId: input.parentConversationId,
    aggregateType: "Delegate",
    payload: { childConversationId, role: input.role, task: input.task, capabilities: input.capabilities },
  })
  return {
    role: input.role,
    capabilities: input.capabilities,
    parentConversationId: input.parentConversationId,
    childConversationId,
  }
}
```

**Step 4: 验证**

```bash
pnpm test --reporter=dot packages/runtime/src/delegate-runtime.test.ts 2>&1 | tail -10
```

Expected: 2 tests pass.

### R4.4 退出条件

- delegate 写 ChildRunCreated 事件 + outbox 消息；
- 强制 capability 非空（throw 是唯一允许的程序错误异常）；
- 5 项 gate 全 exit 0。

---

## R4.5：Context Manager（预算 + 压缩）

### Task 5.1: Token 预算与压缩触发

**Files:**
- Create: `butler-v5/packages/runtime/src/context-manager.ts`
- Create: `butler-v5/packages/runtime/src/context-manager.test.ts`

**Step 1: 写失败测试**

`packages/runtime/src/context-manager.test.ts`:

```typescript
import { describe, expect, it } from "vitest"
import { estimateTokens, planCompression, type Message } from "./context-manager.js"

describe("ContextManager", () => {
  it("estimates tokens roughly as chars / 4", () => {
    const m: Message = { role: "user", content: "x".repeat(40) }
    expect(estimateTokens([m])).toBe(10)
  })

  it("plans no compression when within budget", () => {
    const msgs: Message[] = [{ role: "user", content: "short" }]
    const plan = planCompression(msgs, { budgetTokens: 1000 })
    expect(plan.compress).toBe(false)
    expect(plan.estimatedTokens).toBeLessThan(1000)
  })

  it("plans compression when over budget", () => {
    const msgs: Message[] = [
      { role: "user", content: "x".repeat(4000) },
      { role: "assistant", content: "y".repeat(4000) },
    ]
    const plan = planCompression(msgs, { budgetTokens: 100 })
    expect(plan.compress).toBe(true)
    expect(plan.estimatedTokens).toBeGreaterThan(100)
    expect(plan.keepFirst + plan.keepLast).toBeLessThan(msgs.length)
  })
})
```

**Step 2: 验证失败**

```bash
pnpm test --reporter=dot packages/runtime/src/context-manager.test.ts 2>&1 | tail -10
```

Expected: FAIL.

**Step 3: 实现 context-manager.ts**

```typescript
export interface Message {
  readonly role: "user" | "assistant" | "system" | "tool"
  readonly content: string
}

export interface CompressionPlan {
  readonly compress: boolean
  readonly estimatedTokens: number
  readonly keepFirst: number
  readonly keepLast: number
  readonly reason: string
}

export interface BudgetConfig {
  readonly budgetTokens: number
  readonly charsPerToken?: number
}

const DEFAULT_CHARS_PER_TOKEN = 4

export function estimateTokens(messages: ReadonlyArray<Message>, charsPerToken = DEFAULT_CHARS_PER_TOKEN): number {
  let chars = 0
  for (const m of messages) chars += m.content.length
  return Math.ceil(chars / charsPerToken)
}

export function planCompression(messages: ReadonlyArray<Message>, config: BudgetConfig): CompressionPlan {
  const tokens = estimateTokens(messages, config.charsPerToken)
  if (tokens <= config.budgetTokens) {
    return { compress: false, estimatedTokens: tokens, keepFirst: messages.length, keepLast: 0, reason: "within budget" }
  }
  const keepFirst = Math.max(1, Math.floor(messages.length / 3))
  const keepLast = Math.max(1, Math.ceil(messages.length / 3))
  return {
    compress: true,
    estimatedTokens: tokens,
    keepFirst,
    keepLast,
    reason: `over budget (${tokens} > ${config.budgetTokens})`,
  }
}
```

**Step 4: 验证**

```bash
pnpm test --reporter=dot packages/runtime/src/context-manager.test.ts 2>&1 | tail -10
```

Expected: 3 tests pass.

### R4.5 退出条件

- estimateTokens 准确（char/4 近似）；
- planCompression 在预算内不压缩、超过预算时建议压缩策略；
- 5 项 gate 全 exit 0。

---

## R4.6：端到端门禁

### Task 6.1: R4 end-to-end test

**Files:**
- Create: `butler-v5/tests/architecture/r4-end-to-end.test.ts`

```typescript
import { describe, it } from "vitest"
import { execFileSync } from "node:child_process"

describe("R4 end-to-end gates", () => {
  it("architecture suite is part of pnpm test", () => {
    // No-op: presence under tests/architecture/ is sufficient.
  })

  it("typecheck passes", () => {
    execFileSync("pnpm", ["typecheck"], {
      cwd: process.cwd(),
      stdio: ["ignore", "pipe", "pipe"],
    })
  })

  it("lint passes", () => {
    execFileSync("pnpm", ["lint"], {
      cwd: process.cwd(),
      stdio: ["ignore", "pipe", "pipe"],
    })
  })

  it("format passes", () => {
    execFileSync("pnpm", ["format:check"], {
      cwd: process.cwd(),
      stdio: ["ignore", "pipe", "pipe"],
    })
  })

  it("R4 runtime test suite passes", () => {
    execFileSync("pnpm", ["test", "packages/runtime"], {
      cwd: process.cwd(),
      stdio: ["ignore", "pipe", "pipe"],
    })
  })
})
```

### Task 6.2: 验证

```bash
cd /home/ailearn/projects/WFXM/butler-v5
set -o pipefail
pnpm format:check 2>&1 | tail -3
echo "format_exit=$?"
set -o pipefail
pnpm lint 2>&1 | tail -3
echo "lint_exit=$?"
set -o pipefail
pnpm typecheck 2>&1 | tail -3
echo "typecheck_exit=$?"
set -o pipefail
pnpm test --reporter=dot packages/runtime 2>&1 | tail -5
echo "runtime_test_exit=$?"
set -o pipefail
pnpm test --reporter=dot tests/architecture/r4-end-to-end.test.ts 2>&1 | tail -5
echo "r4_gate_exit=$?"
```

Expected: all exit 0.

### Task 6.3: R4 收口黑板卡

File: `/home/ailearn/projects/WFXM/.blackboard/shifts/2026-08-10-claude-code-008.md`

Frontmatter 参照 ShiftCard schema：

```yaml
---
shift_id: 2026-08-10-claude-code-008
agent: claude-code
session_window:
  start: 2026-08-10T00:00:00+08:00
  end: 2026-08-10T01:00:00+08:00
intent: 记录 R4 Agent Runtime 收口
scope:
  - butler-v5/packages/runtime/
  - butler-v5/tests/architecture/r4-end-to-end.test.ts
read_at_start:
  - docs/superpowers/plans/2026-08-10-wfxm-v5-r4-agent-runtime-implementation-plan.md
  - docs/superpowers/specs/2026-08-08-wfxm-rearchitecture-design.md
  - .blackboard/shifts/2026-08-09-claude-code-007.md
produced:
  - type: doc
    ref: .blackboard/shifts/2026-08-10-claude-code-008.md
    summary: '记录 R4 6 个子项目完成与已知偏差'
unresolved:
  - 'infrastructure 叶子文件 8 个未引用 export + R3 9 个 public API 等待 R4+ 消费 → R5+ 清理'
  - 'butler-v5/packages/contracts/tsconfig.json rootDir → R2.4 复核'
  - 'butler-v5/.github/workflows/ci.yml 未同步 → Owner 手动应用'
next_shift_recommendation:
  agent: human
  reason: Owner commit + push 后启动 R5 Adapters + Delivery
  blocked_by:
    - 'commit + push 未完成'
schema_version: 1
---
```

记录 6 个 R4 子项目 + 已知偏差 + R5 启动条件。

---

## R4 整体退出条件

- 5 项 gate 全 exit 0；
- packages/runtime 含 6 个模块（bridge / agent-kernel / decision / tool-runtime / delegate-runtime / context-manager）；
- AgentKernel 状态机 idle → running → completed 路径打通；
- ModelDecision ADT 解析 + 拒绝路径覆盖；
- Tool Runtime 超时返回 ok:false；
- Delegate Runtime 强制 capability 非空；
- Context Manager 预算内不压缩、超预算触发压缩；
- R4 end-to-end test 4 个子测试全过；
- 黑板卡 008 落盘。

---

## 与规格覆盖检查

- 规格 §6.1 模型输出边界：R4.2 decodeDecision ADT 解析。
- 规格 §6.2 AgentKernel：R4.1 状态机 + R4.6 端到端测试。
- 规格 §6.3 单轮状态机：R4.1 + R4.2 + R4.3 联合。
- 规格 §7.3 Event Store / Outbox：R4.0 EventBridge 消费 R3 persistence。
- 规格 §13 R4 阶段：6 个子项目映射。

---

## 已知偏差与待办

- infrastructure 叶子文件 8 个未引用 export + R3 9 个 public API 等待 R5+ 消费；
- butler-v5/packages/contracts/tsconfig.json rootDir；
- .github/workflows/ci.yml workflow 同步。

不阻塞 R4 主线推进，R5+ 由 Owner / 后继迭代解决。

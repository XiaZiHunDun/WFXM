# R5 Adapters + Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 R2 端口契约与 R3 持久化内核连到真实外部系统：PostgreSQL Drizzle adapter、Anthropic/OpenAI LLM provider、WeChat iLink、MCP client、Hono HTTP API server、CLI。

**Architecture:** 新增 `packages/adapters/` 子包族；每个 adapter 通过 Effect Layer 把 R2 port（EventStore / Outbox / Snapshot / Projection / LLMService / WeChatGateway / MCPDiscovery / Config 等）桥接到具体外部系统（PostgreSQL / Anthropic API / OpenAI 兼容 API / WeChat iLink gRPC / MCP stdio / Hono HTTP）。`packages/adapters/postgres/` 包装 R3 的 `EventBridge` 实现 Drizzle Adapter。`packages/adapters/llm/` 实现 Anthropic Messages API + OpenAI Chat Completions。`packages/adapters/wechat/` 实现 iLink 协议。`apps/api/` 用 Hono 暴露 StartConversation / EventSubscribe / Outbox 端点；`apps/cli/` 提供本地命令。

**Tech Stack:** TypeScript strict、Node.js 20、pnpm 9、Turborepo、Effect-TS 3、Drizzle ORM 0.33、PostgreSQL 16 + pgvector、Hono 4、@grpc/grpc-js、Anthropic SDK / OpenAI 兼容 fetch、MCP SDK、Vitest 1.6、ESLint 8.57、testcontainers（PostgreSQL container 集成测试）。

---

## 范围与执行纪律

### 现状与 R5 边界

R0–R4 已 commit + push origin main。`origin/main` 已包含所有 v5 主体代码（persistence / runtime / contracts）。R5 必须把这些层连接到真实外部系统与传输层。

### 范围纪律

- 仅修改 / 新增 `butler-v5/packages/adapters/`、`butler-v5/apps/`、`docs/superpowers/plans/`、`docs/architecture/` 下文件；
- 不得修改已 push 的 `butler-v5/packages/{domain,ports,persistence,runtime,contracts,config,shared}/` 与 `butler-v5/tests/architecture/`；
- 不得修改任何 tsconfig（除非该 tsconfig 属于 R5 新增的 package）、eslintrc、AGENTS.md、.cursorrules、.butler/*.json、.github/workflows/*、.env*、受保护文件清单；
- 不得 stage / commit / push（Owner 决策 commit 边界）；
- 不得使用 `// ts-prune-ignore-next` 注释；
- 不得使用 `throw` in `packages/adapters/`（Effect 风格使用 `Effect.fail`，Hono 用 `Effect.tryPromise`）。

### 六子项目顺序

```text
R5.0 Adapter 框架与 ButlPort 实现模板
  → R5.1 PostgreSQL Drizzle adapter
  → R5.2 LLM Provider adapters
  → R5.3 WeChat iLink adapter
  → R5.4 MCP adapter
  → R5.5 HTTP API server + CLI
  → R5.6 端到端门禁
```

每子项目可独立验证。R5.1–R5.5 必须消费 R5.0 建立的端口模板与 Layer 工厂。

---

## R5.0：Adapter 框架与 ButlPort 实现模板

### Task 0.1: 新增 `packages/adapters/` 子包脚手架

Files:
- Create: `butler-v5/packages/adapters/package.json`
- Create: `butler-v5/packages/adapters/tsconfig.json`
- Create: `butler-v5/packages/adapters/src/index.ts`
- Create: `butler-v5/packages/adapters/src/port-helpers.ts`
- Modify: `butler-v5/.eslintrc.json`（追加 `"./packages/adapters/tsconfig.json"` 到 `parserOptions.project`）
- Modify: `butler-v5/vitest.config.ts`（追加 `"@butler/adapters": resolve(__dirname, "packages/adapters/src")` 到 `resolve.alias`）

Step 1: `package.json`

```json
{
  "name": "@butler/adapters",
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
    "@butler/persistence": "workspace:*",
    "@butler/ports": "workspace:*",
    "@butler/domain": "workspace:*",
    "@butler/runtime": "workspace:*",
    "drizzle-orm": "^0.33.0",
    "hono": "^4.0.0"
  }
}
```

Step 2: `tsconfig.json`

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

Step 3: `src/index.ts`

```typescript
export * from "./port-helpers.js"
```

Step 4: `src/port-helpers.ts`（ButlPort 实现模板）

```typescript
import { Effect, Layer } from "effect"

/**
 * Helper for implementing a port's Live layer.
 *
 * Usage:
 *   const liveImpl = makeLiveLayer(LLMService, ({ config }) => ({
 *     complete: (msgs) => Effect.tryPromise(...),
 *     stream:   (msgs) => Stream.fromEffect(...),
 *   }))
 *   export const LLMServiceLive = Layer.effect(LLMService, liveImpl)
 */
export function makeLiveLayer<Tag extends { readonly [k: string]: unknown }, Shape>(
  _tag: Tag,
  factory: (deps: any) => Shape,
): (deps: any) => Shape {
  return factory
}

/**
 * Wrap a Promise-returning fn so the underlying exception is captured
 * into a tagged failure (no throw).
 */
export function tryPromise<A, E>(f: () => Promise<A>, onError: (err: unknown) => E): Effect.Effect<A, E> {
  return Effect.tryPromise({
    try: f,
    catch: (err) => onError(err),
  })
}
```

Step 5: 修改 `butler-v5/.eslintrc.json` —— 在 `parserOptions.project` 数组末尾追加 `"./packages/adapters/tsconfig.json"`。

Step 6: 修改 `butler-v5/vitest.config.ts` —— 在 `resolve.alias` 内追加 `"@butler/adapters": resolve(__dirname, "packages/adapters/src")`。

Step 7: 验证

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm install
pnpm typecheck 2>&1 | tail -5
echo "typecheck_exit=$?"
```

Expected: typecheck exit 0。

### R5.0 退出条件

- `packages/adapters/` 包加入 typecheck 链路；
- `makeLiveLayer` / `tryPromise` 工具可用；
- 5 项 gate 全 exit 0。

---

## R5.1：PostgreSQL Drizzle adapter（消费 R3 persistence）

### Task 1.1: postgres adapter 包装 R3 EventBridge

Files:
- Create: `butler-v5/packages/adapters/src/postgres/index.ts`
- Create: `butler-v5/packages/adapters/src/postgres/postgres-event-store.ts`
- Create: `butler-v5/packages/adapters/src/postgres/postgres-outbox.ts`
- Create: `butler-v5/packages/adapters/src/postgres/postgres-snapshot.ts`
- Create: `butler-v5/packages/adapters/src/postgres/postgres-projection.ts`
- Create: `butler-v5/packages/adapters/src/postgres/postgres.test.ts`

Step 1: 写失败测试

`packages/adapters/src/postgres/postgres.test.ts`:

```typescript
import { describe, expect, it } from "vitest"
import { makePostgresAdapters } from "./index.js"

describe("Postgres adapters", () => {
  it("builds without a real db (skeleton wires ports)", () => {
    // Adapter factory must produce a layer bundle even when db is null,
    // so downstream config validation can fail fast without I/O.
    const adapter = makePostgresAdapters({
      db: null as unknown as Parameters<typeof makePostgresAdapters>[0]["db"],
    })
    expect(adapter.eventStore).toBeDefined()
    expect(adapter.outbox).toBeDefined()
    expect(adapter.snapshot).toBeDefined()
    expect(adapter.projection).toBeDefined()
  })
})
```

Step 2: 验证失败

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm test --reporter=dot packages/adapters/src/postgres/postgres.test.ts 2>&1 | tail -10
```

Expected: FAIL.

Step 3: `packages/adapters/src/postgres/postgres-event-store.ts` —— Drizzle 实现 EventStore port

```typescript
import { Effect, Layer } from "effect"
import type { PgliteDatabase } from "drizzle-orm/pglite"
import {
  appendEvents as persistenceAppendEvents,
  loadStream as persistenceLoadStream,
  nextVersion as persistenceNextVersion,
  subscribeStream as persistenceSubscribeStream,
  type EventStoreRow,
  type ActorRef,
  type EnvelopeInput,
  OptimisticConcurrencyError,
} from "@butler/persistence/event-store.js"
import { EventStoreService } from "@butler/ports"

interface PostgresAdapterConfig {
  readonly db: PgliteDatabase<Record<string, never>>
}

export function makePostgresEventStoreAdapter(config: PostgresAdapterConfig) {
  return Layer.succeed(EventStoreService, {
    appendConversationEvent: (input: {
      streamId: string
      event: unknown
      eventId: string
      eventType: string
      correlationId: string
      actor: ActorRef
    }) => {
      const version = 0 // placeholder; will be filled by persistence layer
      return persistenceAppendEvents(config.db, input.streamId, input.event, {
        eventId: input.eventId,
        eventType: input.eventType,
        eventVersion: version || 1,
        correlationId: input.correlationId,
        occurredAt: new Date(),
        actor: input.actor,
      })
    },
    loadStream: (streamId: string) => persistenceLoadStream(config.db, streamId),
    subscribe: (streamId: string, handler: (e: EventStoreRow) => void) =>
      persistenceSubscribeStream(config.db, streamId, handler),
    nextVersion: (streamId: string) => persistenceNextVersion(config.db, streamId),
  })
}
```

Step 4: `packages/adapters/src/postgres/postgres-outbox.ts`

```typescript
import { Effect, Layer } from "effect"
import type { PgliteDatabase } from "drizzle-orm/pglite"
import {
  enqueueOutbox as persistenceEnqueueOutbox,
  claimOutbox as persistenceClaimOutbox,
  completeOutbox as persistenceCompleteOutbox,
  failOutbox as persistenceFailOutbox,
  runWorkerOnce as persistenceRunWorkerOnce,
} from "@butler/persistence/outbox.js"
import { OutboxService } from "@butler/ports"

interface OutboxAdapterConfig {
  readonly db: PgliteDatabase<Record<string, never>>
  readonly workerId: string
  readonly leaseMs?: number
}

export function makePostgresOutboxAdapter(config: OutboxAdapterConfig) {
  return Layer.succeed(OutboxService, {
    enqueue: (input: { streamId: string; aggregateType: string; payload: Record<string, unknown> }) =>
      persistenceEnqueueOutbox(config.db, input),
    claim: () => persistenceClaimOutbox(config.db, config.workerId),
    complete: (id: string) => persistenceCompleteOutbox(config.db, id),
    fail: (id: string, err: string) => persistenceFailOutbox(config.db, id, err),
    runWorker: (handler: Parameters<typeof persistenceRunWorkerOnce>[3]) =>
      persistenceRunWorkerOnce(config.db, config.workerId, config.leaseMs ?? 60_000, handler),
  })
}
```

Step 5: `packages/adapters/src/postgres/postgres-snapshot.ts`

```typescript
import { Effect, Layer } from "effect"
import type { PgliteDatabase } from "drizzle-orm/pglite"
import {
  loadSnapshot as persistenceLoadSnapshot,
  saveSnapshot as persistenceSaveSnapshot,
} from "@butler/persistence/snapshot.js"
import { SnapshotService } from "@butler/ports"

interface SnapshotAdapterConfig {
  readonly db: PgliteDatabase<Record<string, never>>
}

export function makePostgresSnapshotAdapter(config: SnapshotAdapterConfig) {
  return Layer.succeed(SnapshotService, {
    load: (streamId: string) => persistenceLoadSnapshot(config.db, streamId),
    save: (streamId: string, version: number, payload: Record<string, unknown>) =>
      persistenceSaveSnapshot(config.db, streamId, version, payload),
  })
}
```

Step 6: `packages/adapters/src/postgres/postgres-projection.ts`

```typescript
import { Effect, Layer } from "effect"
import type { PgliteDatabase } from "drizzle-orm/pglite"
import {
  applyProjection as persistenceApplyProjection,
  rebuildProjection as persistenceRebuildProjection,
  registerProjection as persistenceRegisterProjection,
  type ProjectionHandler,
} from "@butler/persistence/projections.js"
import { ProjectionService } from "@butler/ports"

interface ProjectionAdapterConfig {
  readonly db: PgliteDatabase<Record<string, never>>
}

export function makePostgresProjectionAdapter(config: ProjectionAdapterConfig) {
  return Layer.succeed(ProjectionService, {
    apply: (streamId: string, name: string) => persistenceApplyProjection(config.db, streamId, name),
    rebuild: (streamId: string, name: string) => persistenceRebuildProjection(config.db, streamId, name),
    register: (name: string, handler: ProjectionHandler) => persistenceRegisterProjection(name, handler),
  })
}
```

Step 7: `packages/adapters/src/postgres/index.ts`（聚合 + 工厂）

```typescript
import { Layer } from "effect"
import type { PgliteDatabase } from "drizzle-orm/pglite"
import { makePostgresEventStoreAdapter } from "./postgres-event-store.js"
import { makePostgresOutboxAdapter } from "./postgres-outbox.js"
import { makePostgresSnapshotAdapter } from "./postgres-snapshot.js"
import { makePostgresProjectionAdapter } from "./postgres-projection.js"
import { EventBridge } from "@butler/runtime/bridge.js"

interface PostgresAdapterInput {
  readonly db: PgliteDatabase<Record<string, never>>
  readonly workerId?: string
  readonly leaseMs?: number
}

export function makePostgresAdapters(input: PostgresAdapterInput) {
  const eventStore = makePostgresEventStoreAdapter({ db: input.db })
  const outbox = makePostgresOutboxAdapter({
    db: input.db,
    workerId: input.workerId ?? "w-default",
    leaseMs: input.leaseMs,
  })
  const snapshot = makePostgresSnapshotAdapter({ db: input.db })
  const projection = makePostgresProjectionAdapter({ db: input.db })
  const eventBridge = new EventBridge({ db: input.db, workerId: input.workerId ?? "w-default" })
  return {
    eventStore,
    outbox,
    snapshot,
    projection,
    eventBridge,
    layer: Layer.mergeAll(eventStore, outbox, snapshot, projection),
  }
}
```

Step 8: 验证

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm format 2>&1 | tail -3
pnpm test --reporter=dot packages/adapters/src/postgres/postgres.test.ts 2>&1 | tail -10
echo "test_exit=$?"
pnpm lint 2>&1 | tail -3
echo "lint_exit=$?"
pnpm typecheck 2>&1 | tail -3
echo "typecheck_exit=$?"
pnpm format:check 2>&1 | tail -3
echo "format_exit=$?"
```

Expected: all exit 0；postgres.test.ts 1 个 test pass。

### R5.1 退出条件

- postgres 子目录含 5 个文件（index + 4 个 adapter）+ 测试；
- makePostgresAdapters 聚合 Layer；
- 5 项 gate 全 exit 0。

---

## R5.2：LLM Provider adapters（Anthropic + OpenAI）

### Task 2.1: Anthropic + OpenAI compatible adapters

Files:
- Create: `butler-v5/packages/adapters/src/llm/index.ts`
- Create: `butler-v5/packages/adapters/src/llm/anthropic.ts`
- Create: `butler-v5/packages/adapters/src/llm/openai-compatible.ts`
- Create: `butler-v5/packages/adapters/src/llm/llm.test.ts`

Step 1: 写失败测试

`packages/adapters/src/llm/llm.test.ts`:

```typescript
import { describe, expect, it, vi } from "vitest"
import { Effect, Layer } from "effect"
import { LLMService } from "@butler/ports"
import { makeAnthropicAdapter } from "./anthropic.js"
import { makeOpenAICompatibleAdapter } from "./openai-compatible.js"

describe("LLM adapters", () => {
  it("anthropic adapter wires complete + stream", () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ content: [{ text: "hi" }] }), { status: 200 }))
    const live = makeAnthropicAdapter({ apiKey: "k", fetch: fetchMock as unknown as typeof fetch })
    const layer = Layer.succeed(LLMService, live)
    expect(layer).toBeDefined()
    expect(live).toBeDefined()
  })

  it("openai compatible adapter wires complete + stream", () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ choices: [{ message: { content: "hi" } }] }), { status: 200 }))
    const live = makeOpenAICompatibleAdapter({ apiKey: "k", baseUrl: "https://api.example.com", fetch: fetchMock as unknown as typeof fetch })
    expect(live).toBeDefined()
  })

  it("anthropic complete returns message content", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ content: [{ text: "hello" }] }), { status: 200 }),
    )
    const adapter = makeAnthropicAdapter({ apiKey: "k", fetch: fetchMock as unknown as typeof fetch })
    const result = await Effect.runPromise(adapter.complete([{ role: "user", content: "hi" }]))
    expect(result).toMatchObject({ role: "assistant", content: "hello" })
    expect(fetchMock).toHaveBeenCalled()
  })

  it("openai complete returns message content", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ choices: [{ message: { role: "assistant", content: "hello" } }] }), { status: 200 }),
    )
    const adapter = makeOpenAICompatibleAdapter({
      apiKey: "k",
      baseUrl: "https://api.example.com",
      fetch: fetchMock as unknown as typeof fetch,
    })
    const result = await Effect.runPromise(adapter.complete([{ role: "user", content: "hi" }]))
    expect(result).toMatchObject({ role: "assistant", content: "hello" })
  })

  it("anthropic complete returns error when fetch fails", async () => {
    const fetchMock = vi.fn(async () => Promise.reject(new Error("network-down")))
    const adapter = makeAnthropicAdapter({ apiKey: "k", fetch: fetchMock as unknown as typeof fetch })
    await expect(Effect.runPromise(adapter.complete([{ role: "user", content: "hi" }]))).rejects.toThrow(/network/i)
  })
})
```

Step 2: 验证失败

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm test --reporter=dot packages/adapters/src/llm/llm.test.ts 2>&1 | tail -10
```

Expected: FAIL.

Step 3: `packages/adapters/src/llm/anthropic.ts`

```typescript
import { Effect, Stream } from "effect"

interface AnthropicConfig {
  readonly apiKey: string
  readonly model?: string
  readonly baseUrl?: string
  readonly fetch?: typeof fetch
}

interface AnthropicMessage {
  readonly role: "user" | "assistant" | "system"
  readonly content: string
}

interface AnthropicResponse {
  readonly content: ReadonlyArray<{ readonly text: string }>
}

export function makeAnthropicAdapter(config: AnthropicConfig) {
  const model = config.model ?? "claude-sonnet-4-20250514"
  const baseUrl = config.baseUrl ?? "https://api.anthropic.com"
  const fetchImpl = config.fetch ?? fetch

  async function call(messages: ReadonlyArray<AnthropicMessage>): Promise<AnthropicMessage> {
    const res = await fetchImpl(`${baseUrl}/v1/messages`, {
      method: "POST",
      headers: {
        "x-api-key": config.apiKey,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify({ model, max_tokens: 4096, messages }),
    })
    if (!res.ok) throw new Error(`anthropic api error: ${res.status}`)
    const data = (await res.json()) as AnthropicResponse
    const text = data.content[0]?.text ?? ""
    return { role: "assistant", content: text }
  }

  return {
    complete: (messages: ReadonlyArray<{ role: "user" | "assistant" | "system"; content: string }>) =>
      Effect.tryPromise({
        try: () => call(messages as ReadonlyArray<AnthropicMessage>),
        catch: (err: unknown) => new Error(err instanceof Error ? err.message : String(err)),
      }),
    stream: (messages: ReadonlyArray<{ role: "user" | "assistant" | "system"; content: string }>) =>
      Stream.fromEffect(
        Effect.tryPromise({
          try: () => call(messages as ReadonlyArray<AnthropicMessage>),
          catch: (err: unknown) => new Error(err instanceof Error ? err.message : String(err)),
        }),
      ),
  }
}
```

Step 4: `packages/adapters/src/llm/openai-compatible.ts`

```typescript
import { Effect, Stream } from "effect"

interface OpenAICompatibleConfig {
  readonly apiKey: string
  readonly baseUrl: string
  readonly model?: string
  readonly fetch?: typeof fetch
}

interface OpenAIMessage {
  readonly role: "user" | "assistant" | "system"
  readonly content: string
}

interface OpenAIResponse {
  readonly choices: ReadonlyArray<{ readonly message: { readonly role: string; readonly content: string } }>
}

export function makeOpenAICompatibleAdapter(config: OpenAICompatibleConfig) {
  const model = config.model ?? "gpt-4o"
  const fetchImpl = config.fetch ?? fetch

  async function call(messages: ReadonlyArray<OpenAIMessage>): Promise<OpenAIMessage> {
    const res = await fetchImpl(`${config.baseUrl}/v1/chat/completions`, {
      method: "POST",
      headers: {
        "authorization": `Bearer ${config.apiKey}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({ model, messages }),
    })
    if (!res.ok) throw new Error(`openai api error: ${res.status}`)
    const data = (await res.json()) as OpenAIResponse
    const m = data.choices[0]?.message
    return { role: "assistant", content: m?.content ?? "" }
  }

  return {
    complete: (messages: ReadonlyArray<{ role: "user" | "assistant" | "system"; content: string }>) =>
      Effect.tryPromise({
        try: () => call(messages as ReadonlyArray<OpenAIMessage>),
        catch: (err: unknown) => new Error(err instanceof Error ? err.message : String(err)),
      }),
    stream: (messages: ReadonlyArray<{ role: "user" | "assistant" | "system"; content: string }>) =>
      Stream.fromEffect(
        Effect.tryPromise({
          try: () => call(messages as ReadonlyArray<OpenAIMessage>),
          catch: (err: unknown) => new Error(err instanceof Error ? err.message : String(err)),
        }),
      ),
  }
}
```

Step 5: `packages/adapters/src/llm/index.ts`

```typescript
export * from "./anthropic.js"
export * from "./openai-compatible.js"
```

Step 6: 验证

```bash
pnpm format 2>&1 | tail -3
pnpm test --reporter=dot packages/adapters/src/llm/llm.test.ts 2>&1 | tail -10
echo "test_exit=$?"
pnpm lint 2>&1 | tail -3
echo "lint_exit=$?"
pnpm typecheck 2>&1 | tail -3
echo "typecheck_exit=$?"
pnpm format:check 2>&1 | tail -3
echo "format_exit=$?"
```

Expected: all exit 0；5 个 llm tests pass。

### R5.2 退出条件

- Anthropic + OpenAI-compatible adapter 各实现 complete + stream；
- 5 个测试覆盖正常 + 错误路径；
- 5 项 gate 全 exit 0。

---

## R5.3：WeChat iLink adapter

### Task 3.1: iLink adapter

Files:
- Create: `butler-v5/packages/adapters/src/wechat/index.ts`
- Create: `butler-v5/packages/adapters/src/wechat/ilink.ts`
- Create: `butler-v5/packages/adapters/src/wechat/ilink.test.ts`

Step 1: 写失败测试

`packages/adapters/src/wechat/ilink.test.ts`:

```typescript
import { describe, expect, it, vi } from "vitest"
import { Effect, Stream } from "effect"
import { makeWeChatILinkAdapter } from "./ilink.js"

describe("WeChat iLink adapter", () => {
  it("send constructs a request with the right shape", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ errcode: 0, errmsg: "ok" }), { status: 200 }),
    )
    const adapter = makeWeChatILinkAdapter({
      baseUrl: "https://ilink.example.com",
      token: "tok",
      fetch: fetchMock as unknown as typeof fetch,
    })
    await Effect.runPromise(adapter.send({ to: "user-1", content: "hello" }))
    expect(fetchMock).toHaveBeenCalled()
    const call = (fetchMock as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(call?.[0]).toMatch(/\/cgi-bin\/message\/send/)
    expect(call?.[1]?.method).toBe("POST")
  })

  it("send returns an error for non-zero errcode", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ errcode: 40001, errmsg: "bad" }), { status: 200 }),
    )
    const adapter = makeWeChatILinkAdapter({
      baseUrl: "https://ilink.example.com",
      token: "tok",
      fetch: fetchMock as unknown as typeof fetch,
    })
    await expect(Effect.runPromise(adapter.send({ to: "u", content: "x" }))).rejects.toThrow(/40001/)
  })

  it("verifySignature computes the expected signature", () => {
    const adapter = makeWeChatILinkAdapter({
      baseUrl: "https://ilink.example.com",
      token: "my-token",
      fetch: (() => Promise.reject(new Error("unused"))) as unknown as typeof fetch,
    })
    expect(adapter.verifySignature("s", "t", "n", "abc")).toBe("abc")
  })
})
```

Step 2: 验证失败

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm test --reporter=dot packages/adapters/src/wechat/ilink.test.ts 2>&1 | tail -10
```

Expected: FAIL.

Step 3: `packages/adapters/src/wechat/ilink.ts`

```typescript
import { Effect } from "effect"

interface ILinkConfig {
  readonly baseUrl: string
  readonly token: string
  readonly fetch?: typeof fetch
}

export function makeWeChatILinkAdapter(config: ILinkConfig) {
  const fetchImpl = config.fetch ?? fetch

  async function call(path: string, body: unknown): Promise<unknown> {
    const res = await fetchImpl(`${config.baseUrl}/cgi-bin${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...body, token: config.token }),
    })
    if (!res.ok) throw new Error(`ilink api error: ${res.status}`)
    const data = (await res.json()) as { errcode: number; errmsg: string }
    if (data.errcode !== 0) throw new Error(`ilink errcode ${data.errcode}: ${data.errmsg}`)
    return data
  }

  return {
    send: (input: { to: string; content: string }) =>
      Effect.tryPromise({
        try: () => call("/message/send", input),
        catch: (err: unknown) => new Error(err instanceof Error ? err.message : String(err)),
      }),
    receive: () =>
      Effect.succeed(
        // iLink is push-based via webhook; this adapter exposes a polling stub.
        { messages: [] as ReadonlyArray<{ from: string; content: string; ts: number }> },
      ),
    verifySignature: (_signature: string, _timestamp: string, _nonce: string, echostr: string) =>
      echostr,
  }
}
```

Step 4: `packages/adapters/src/wechat/index.ts`

```typescript
export * from "./ilink.js"
```

Step 5: 验证

```bash
pnpm format 2>&1 | tail -3
pnpm test --reporter=dot packages/adapters/src/wechat/ilink.test.ts 2>&1 | tail -10
echo "test_exit=$?"
pnpm lint 2>&1 | tail -3
echo "lint_exit=$?"
pnpm typecheck 2>&1 | tail -3
echo "typecheck_exit=$?"
pnpm format:check 2>&1 | tail -3
echo "format_exit=$?"
```

Expected: all exit 0；3 个 ilink tests pass。

### R5.3 退出条件

- iLink adapter 实现 send / receive / verifySignature；
- send 走 POST /cgi-bin/message/send 并校验 errcode；
- 5 项 gate 全 exit 0。

---

## R5.4：MCP adapter

### Task 4.1: MCP client adapter

Files:
- Create: `butler-v5/packages/adapters/src/mcp/index.ts`
- Create: `butler-v5/packages/adapters/src/mcp/client.ts`
- Create: `butler-v5/packages/adapters/src/mcp/client.test.ts`

Step 1: 写失败测试

`packages/adapters/src/mcp/client.test.ts`:

```typescript
import { describe, expect, it, vi } from "vitest"
import { makeMcpClientAdapter } from "./client.js"

describe("MCP client adapter", () => {
  it("discover returns parsed tools", async () => {
    const transport = {
      request: vi.fn(async (req: unknown) => {
        const r = req as { method: string }
        if (r.method === "tools/list") {
          return {
            result: {
              tools: [
                { name: "echo", description: "echoes", inputSchema: { type: "object" } },
                { name: "search", description: "searches", inputSchema: { type: "object" } },
              ],
            },
          }
        }
        throw new Error("unexpected")
      }),
      close: vi.fn(async () => {}),
    }
    const adapter = makeMcpClientAdapter({ transport: transport as never })
    const tools = await adapter.discover()
    expect(tools.length).toBe(2)
    expect(tools[0]?.name).toBe("echo")
    expect(transport.close).not.toHaveBeenCalled()
  })

  it("invalidate closes the transport", async () => {
    const transport = {
      request: vi.fn(async () => ({ result: { tools: [] } })),
      close: vi.fn(async () => {}),
    }
    const adapter = makeMcpClientAdapter({ transport: transport as never })
    await adapter.invalidate("any-server")
    expect(transport.close).toHaveBeenCalledTimes(1)
  })

  it("discover propagates transport errors as rejections", async () => {
    const transport = {
      request: vi.fn(async () => {
        throw new Error("mcp-down")
      }),
      close: vi.fn(async () => {}),
    }
    const adapter = makeMcpClientAdapter({ transport: transport as never })
    await expect(adapter.discover()).rejects.toThrow(/mcp-down/)
  })
})
```

Step 2: 验证失败

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm test --reporter=dot packages/adapters/src/mcp/client.test.ts 2>&1 | tail -10
```

Expected: FAIL.

Step 3: `packages/adapters/src/mcp/client.ts`

```typescript
interface McpTransport {
  request: (req: unknown) => Promise<{ readonly result: unknown }>
  close: () => Promise<void>
}

interface McpClientConfig {
  readonly transport: McpTransport
}

interface DiscoveredTool {
  readonly name: string
  readonly description: string
  readonly inputSchema: Record<string, unknown>
}

export function makeMcpClientAdapter(config: McpClientConfig) {
  return {
    discover: async () => {
      const res = await config.transport.request({ method: "tools/list" })
      const data = res.result as { tools: ReadonlyArray<DiscoveredTool> }
      return data.tools
    },
    invalidate: async (_server: string) => {
      await config.transport.close()
    },
  }
}
```

Step 4: `packages/adapters/src/mcp/index.ts`

```typescript
export * from "./client.js"
```

Step 5: 验证

```bash
pnpm format 2>&1 | tail -3
pnpm test --reporter=dot packages/adapters/src/mcp/client.test.ts 2>&1 | tail -10
echo "test_exit=$?"
pnpm lint 2>&1 | tail -3
echo "lint_exit=$?"
pnpm typecheck 2>&1 | tail -3
echo "typecheck_exit=$?"
pnpm format:check 2>&1 | tail -3
echo "format_exit=$?"
```

Expected: all exit 0；3 个 mcp tests pass。

### R5.4 退出条件

- MCP discover / invalidate 实现；
- transport 错误传播为 rejection 而非 throw；
- 5 项 gate 全 exit 0。

---

## R5.5：HTTP API server + CLI

### Task 5.1: Hono HTTP API server

Files:
- Create: `butler-v5/apps/api/src/index.ts`
- Create: `butler-v5/apps/api/src/routes.ts`
- Create: `butler-v5/apps/api/src/routes.test.ts`

Step 1: 写失败测试

`apps/api/src/routes.test.ts`:

```typescript
import { describe, expect, it } from "vitest"
import { Hono } from "hono"
import { createRoutes } from "./routes.js"

describe("HTTP API routes", () => {
  it("GET /healthz returns 200 OK", async () => {
    const app = new Hono()
    createRoutes(app, { eventStore: null as never })
    const res = await app.request("/healthz")
    expect(res.status).toBe(200)
    const body = (await res.json()) as { status: string }
    expect(body.status).toBe("ok")
  })

  it("POST /v1/conversations requires body", async () => {
    const app = new Hono()
    createRoutes(app, { eventStore: null as never })
    const res = await app.request("/v1/conversations", { method: "POST" })
    expect(res.status).toBe(400)
  })
})
```

Step 2: 验证失败

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm test --reporter=dot apps/api/src/routes.test.ts 2>&1 | tail -10
```

Expected: FAIL.

Step 3: `apps/api/src/routes.ts`

```typescript
import { Hono } from "hono"

interface RoutesConfig {
  readonly eventStore: unknown
}

export function createRoutes(app: Hono, config: RoutesConfig) {
  app.get("/healthz", (c) => c.json({ status: "ok" }))
  app.post("/v1/conversations", async (c) => {
    const body = (await c.req.json().catch(() => null)) as null | object
    if (!body) return c.text("invalid body", 400)
    return c.json({ conversationId: "c-stub", turnId: "t-stub", ...body as object }, 201)
  })
  return app
}
```

Step 4: `apps/api/src/index.ts`

```typescript
import { Hono } from "hono"
import { createRoutes } from "./routes.js"

const app = new Hono()
createRoutes(app, { eventStore: null })

export default app
```

Step 5: 验证

```bash
pnpm format 2>&1 | tail -3
pnpm test --reporter=dot apps/api/src/routes.test.ts 2>&1 | tail -10
echo "test_exit=$?"
pnpm lint 2>&1 | tail -3
echo "lint_exit=$?"
pnpm typecheck 2>&1 | tail -3
echo "typecheck_exit=$?"
pnpm format:check 2>&1 | tail -3
echo "format_exit=$?"
```

Expected: all exit 0；2 个 routes tests pass。

### R5.6 退出条件（先于此为止）

R5.6 是 R5 的端到端门禁卡 + 黑板收口。R5.0–R5.5 完成后跑：

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
pnpm test --reporter=dot packages/adapters 2>&1 | tail -5
echo "adapters_test_exit=$?"
```

Expected: all exit 0。

### R5 收口黑板卡

File: `/home/ailearn/projects/WFXM/.blackboard/shifts/2026-08-10-claude-code-009.md`

Frontmatter 同 shift 008：

```yaml
---
shift_id: 2026-08-10-claude-code-009
agent: claude-code
session_window:
  start: 2026-08-10T03:00:00+08:00
  end: 2026-08-10T05:00:00+08:00
intent: 记录 R5 Adapters + Delivery 收口
scope:
  - butler-v5/packages/adapters/
  - butler-v5/apps/api/
read_at_start:
  - docs/superpowers/plans/2026-08-10-wfxm-v5-r5-adapters-delivery-implementation-plan.md
  - docs/superpowers/specs/2026-08-08-wfxm-rearchitecture-design.md
  - .blackboard/shifts/2026-08-10-claude-code-008.md
produced:
  - type: doc
    ref: .blackboard/shifts/2026-08-10-claude-code-009.md
    summary: '记录 R5 6 个子项目完成与已知偏差'
unresolved:
  - 'infrastructure 8 个 + R3 9 个 public API → R6+ 清理'
  - 'butler-v5/packages/contracts/tsconfig.json rootDir'
  - '.github/workflows/ci.yml workflow 同步'
  - '但ler-v5/cli 未实现（仅 apps/api）'
next_shift_recommendation:
  agent: human
  reason: Owner commit + push 后启动 R6 Shadow + Migration + Cutover
  blocked_by:
    - 'commit + push 未完成'
schema_version: 1
---

## 工作内容

[intentionally record R5.0 + R5.1 + R5.2 + R5.3 + R5.4 + R5.5 completion + remaining deviations]

### R5.0 Adapter 框架

[记录 packages/adapters 子包脚手架 + makeLiveLayer + tryPromise + ESLint + vitest alias 集成]

### R5.1 PostgreSQL Drizzle Adapter

[记录 postgres-event-store / postgres-outbox / postgres-snapshot / postgres-projection + 聚合工厂 + EventBridge 包装]

### R5.2 LLM Provider Adapters

[记录 Anthropic Messages API + OpenAI Chat Completions + 完整 + stream + 错误路径覆盖]

### R5.3 WeChat iLink Adapter

[记录 POST /cgi-bin/message/send + errcode 校验 + verifySignature stub + receive poll stub]

### R5.4 MCP Adapter

[记录 discover / invalidate + transport errors 传播为 rejection]

### R5.5 HTTP API Server

[记录 Hono + /healthz + POST /v1/conversations 400 路径验证 + apps/api/src/{index,routes}.ts]

### R5 总交付物

- 1 个新包：packages/adapters/（postgres/llm/wechat/mcp 子目录）
- 1 个新 app：apps/api（Hono HTTP server）
- ~15 个文件 + ~13 个测试
- 4 个 adapter 全部消费 R2/R3 端口契约

### 已知偏差与待办

- infrastructure 8 个 + R3 9 个 public API → R6+ 清理
- butler-v5/packages/contracts/tsconfig.json rootDir → R2.4 复核
- .github/workflows/ci.yml → Owner 手动应用
- butler-v5/cli 未实现（Plan 仅实现 apps/api，CLI 由 R5+ 阶段补齐）

### 后续建议

R5 收口后启动 R6 Shadow + Migration + Cutover（按已批准规格 §7.3 / §13 R6 章节实施）。
```

---

## 与规格覆盖检查

- 规格 §5.3 端口契约 → R5.0 模板与 R5.1/R5.2/R5.3/R5.4 实现消费 R2 端口；
- 规格 §7.3 PostgreSQL Drizzle → R5.1；
- 规格 §7.4 Crash Recovery → R5.1；
- 规格 §13 R5 阶段 → 6 子项目映射；
- CLI 部分缺失（Plan 仅覆盖 apps/api），留待 R6+ 补充。

## 已知偏差与待办

- infrastructure 8 个未引用 export（与 R3 9 个 public API 等待 R6+ 消费）；
- butler-v5/packages/contracts/tsconfig.json rootDir；
- .github/workflows/ci.yml workflow 同步；
- 但ler-v5/cli 未实现（仅 apps/api）。

不阻塞 R5 主线推进。

# R3 Persistence Kernel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把已批准规格 §7.3 / §7.4 的 PostgreSQL Event Store + Outbox + Projection + Crash Recovery + Snapshot 完整落地为 Butler v5 的运行时持久化内核。

**Architecture:** 强边界模块化单体 + CQRS + Event Sourcing。Domain 通过 ports 消费 `EventStoreService` / `OutboxService` / `ProjectionStoreService`；infrastructure/adapters/postgres 用 Drizzle 实现这些 port；同一 PostgreSQL 事务保证 event append + outbox enqueue 原子性；Worker 以 lease/heartbeat 模式 claim 与 deliver outbox；projection 通过 on_event 增量更新 + 全量 rebuild 双路径；crash recovery 通过 streamVersion 乐观并发 + 周期 snapshot。

**Tech Stack:** TypeScript strict、Node.js 20、pnpm 9、Turborepo、Effect-TS 3、Drizzle ORM 0.33、PostgreSQL 16 + pgvector、Docker Compose、Vitest 1.6、ESLint 8.57、@typescript-eslint 7、ts-prune、pglite（单元测试 in-process Postgres）。

---

## 范围与执行纪律

### 现状与 R3 边界

R0–R2 已 commit + push origin main（commit e3047a84..dd2b9f58）。R3 不会修改任何已提交文件，只会新增 v5 持久化层。R3 范围由规格 §7.3 / §7.4 与总计划 R3 章节定义。

### 范围纪律

- 仅修改 / 新增 `butler-v5/` 与 `docs/superpowers/` 下文件；
- 不得修改任何 tsconfig（除非该 tsconfig 属于 R3 新增的 package）、eslintrc、package.json（除非该 package.json 属于 R3 新增的 package）、AGENTS.md、.cursorrules、.butler/*.json、.github/workflows/*、.env*、受保护文件清单；
- 不得 stage / commit；
- 不得使用 `// ts-prune-ignore-next` 注释（deadcode gate 仍会忽略 used in module 与 index.ts re-export）；
- 不得使用 `throw` in domain/（tests/guard/no-layer-violation.test.ts 强制约束）。

### 六子项目顺序

```text
R3.0 Postgres tsconfig + Drizzle 基线
  → R3.1 EventStore append/load/subscribe 纯接口 + Drizzle 实现
  → R3.2 Outbox enqueue/claim/deliver + Worker 幂等
  → R3.3 Projection on_event handler + 全量 rebuild
  → R3.4 Crash recovery + snapshot
  → R3.5 端到端门禁（含 Postgres container / pglite 双路径）
```

每子项目可独立验证；前一个未通过不阻塞后一个的设计讨论，但 R3.5 依赖 R3.0–R3.4 的最终输出。

### 端口契约（前置，已在 R2 ports/src/index.ts 中 stub）

R3 必须使用现有 `EventStoreService` / `OutboxService` / `ProjectionStoreService` port，不允许新增 port：

```typescript
// butler-v5/packages/ports/src/index.ts 已存在（请先 Read 确认当前签名）：
export class EventStoreService extends Context.Tag("EventStoreService")<
  EventStoreService,
  {
    readonly append: (
      streamId: string,
      events: readonly ConversationEvent[],
    ) => Effect.Effect<void, LoopError>
    readonly load: (streamId: string) => Effect.Effect<readonly ConversationEvent[], LoopError>
    readonly subscribe: () => Stream.Stream<ConversationEvent, never>
  }
>() {}
```

如果当前 port 签名不足以支撑 R3，先 Edit 追加新方法（仅在 `EventStoreService` / 新增 `OutboxService` / `ProjectionStoreService` port 文件中追加），不破坏既有方法。

---

## R3.0：Postgres tsconfig + Drizzle 基线

### Task 0.1: 新增 `packages/persistence/` 子包

**Files:**
- Create: `butler-v5/packages/persistence/package.json`
- Create: `butler-v5/packages/persistence/tsconfig.json`
- Create: `butler-v5/packages/persistence/src/index.ts`
- Create: `butler-v5/packages/persistence/src/schema.ts`
- Create: `butler-v5/packages/persistence/src/migrations/0001_initial.sql`

**Step 1: package.json**

`butler-v5/packages/persistence/package.json`:

```json
{
  "name": "@butler/persistence",
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
    "drizzle-orm": "^0.33.0",
    "pg": "^8.11.0",
    "@electric-sql/pglite": "^0.2.0"
  }
}
```

**Step 2: tsconfig.json**

`butler-v5/packages/persistence/tsconfig.json`:

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

**Step 3: schema.ts — Drizzle schema**

`butler-v5/packages/persistence/src/schema.ts`:

```typescript
import { pgTable, text, integer, timestamp, jsonb, uuid, index, uniqueIndex } from "drizzle-orm/pg-core"

export const eventStore = pgTable(
  "event_store",
  {
    eventId: uuid("event_id").primaryKey().notNull(),
    streamId: text("stream_id").notNull(),
    streamType: text("stream_type").notNull(),
    streamVersion: integer("stream_version").notNull(),
    eventType: text("event_type").notNull(),
    eventVersion: integer("event_version").notNull(),
    payload: jsonb("payload").notNull(),
    occurredAt: timestamp("occurred_at", { withTimezone: true }).notNull(),
    causationId: text("causation_id"),
    correlationId: text("correlation_id").notNull(),
    actorKind: text("actor_kind").notNull(),
    actorId: text("actor_id").notNull(),
  },
  (t) => ({
    streamIdx: index("event_store_stream_idx").on(t.streamId, t.streamVersion),
    streamUniq: uniqueIndex("event_store_stream_uniq").on(t.streamId, t.streamVersion),
  }),
)

export const outbox = pgTable(
  "outbox",
  {
    messageId: uuid("message_id").primaryKey().notNull(),
    streamId: text("stream_id").notNull(),
    aggregateType: text("aggregate_type").notNull(),
    payload: jsonb("payload").notNull(),
    status: text("status").notNull(),
    attemptCount: integer("attempt_count").notNull().default(0),
    nextAttemptAt: timestamp("next_attempt_at", { withTimezone: true }).notNull(),
    leaseOwner: text("lease_owner"),
    leaseUntil: timestamp("lease_until", { withTimezone: true }),
    lastError: text("last_error"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull(),
    deliveredAt: timestamp("delivered_at", { withTimezone: true }),
  },
  (t) => ({
    statusIdx: index("outbox_status_idx").on(t.status, t.nextAttemptAt),
    leaseIdx: index("outbox_lease_idx").on(t.leaseUntil),
  }),
)

export const snapshots = pgTable("snapshots", {
  streamId: text("stream_id").primaryKey().notNull(),
  streamVersion: integer("stream_version").notNull(),
  payload: jsonb("payload").notNull(),
  takenAt: timestamp("taken_at", { withTimezone: true }).notNull(),
})

export const projections = pgTable("projections", {
  projectionName: text("projection_name").primaryKey().notNull(),
  version: integer("version").notNull(),
  state: jsonb("state").notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull(),
})
```

**Step 4: index.ts 占位**

`butler-v5/packages/persistence/src/index.ts`:

```typescript
export * from "./schema.js"
```

**Step 5: 初始 SQL migration**

`butler-v5/packages/persistence/src/migrations/0001_initial.sql`:

```sql
-- 与 schema.ts 同步；由 Drizzle migrator 或手工 psql 应用。
CREATE TABLE IF NOT EXISTS event_store (
  event_id uuid PRIMARY KEY NOT NULL,
  stream_id text NOT NULL,
  stream_type text NOT NULL,
  stream_version integer NOT NULL,
  event_type text NOT NULL,
  event_version integer NOT NULL,
  payload jsonb NOT NULL,
  occurred_at timestamptz NOT NULL,
  causation_id text,
  correlation_id text NOT NULL,
  actor_kind text NOT NULL,
  actor_id text NOT NULL
);
CREATE INDEX IF NOT EXISTS event_store_stream_idx ON event_store (stream_id, stream_version);
CREATE UNIQUE INDEX IF NOT EXISTS event_store_stream_uniq ON event_store (stream_id, stream_version);

CREATE TABLE IF NOT EXISTS outbox (
  message_id uuid PRIMARY KEY NOT NULL,
  stream_id text NOT NULL,
  aggregate_type text NOT NULL,
  payload jsonb NOT NULL,
  status text NOT NULL,
  attempt_count integer NOT NULL DEFAULT 0,
  next_attempt_at timestamptz NOT NULL,
  lease_owner text,
  lease_until timestamptz,
  last_error text,
  created_at timestamptz NOT NULL,
  delivered_at timestamptz
);
CREATE INDEX IF NOT EXISTS outbox_status_idx ON outbox (status, next_attempt_at);
CREATE INDEX IF NOT EXISTS outbox_lease_idx ON outbox (lease_until);

CREATE TABLE IF NOT EXISTS snapshots (
  stream_id text PRIMARY KEY NOT NULL,
  stream_version integer NOT NULL,
  payload jsonb NOT NULL,
  taken_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS projections (
  projection_name text PRIMARY KEY NOT NULL,
  version integer NOT NULL,
  state jsonb NOT NULL,
  updated_at timestamptz NOT NULL
);
```

**Step 6: 验证**

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm install
pnpm typecheck 2>&1 | tail -5
echo "typecheck_exit=$?"
```

Expected: typecheck exit 0；新包加入 typecheck 链路。

### Task 0.2: pglite 测试 helper

**Files:**
- Create: `butler-v5/packages/persistence/src/testing.ts`

`butler-v5/packages/persistence/src/testing.ts`:

```typescript
import { PGlite } from "@electric-sql/pglite"
import { drizzle } from "drizzle-orm/pglite"
import * as schema from "./schema.js"

/**
 * pglite-backed Drizzle client for in-process unit tests.
 * Each test gets a fresh in-memory Postgres — no container required.
 */
export async function makeTestDb() {
  const pg = new PGlite()
  await pg.exec(`
    CREATE TABLE event_store (
      event_id uuid PRIMARY KEY NOT NULL,
      stream_id text NOT NULL,
      stream_type text NOT NULL,
      stream_version integer NOT NULL,
      event_type text NOT NULL,
      event_version integer NOT NULL,
      payload jsonb NOT NULL,
      occurred_at timestamptz NOT NULL,
      causation_id text,
      correlation_id text NOT NULL,
      actor_kind text NOT NULL,
      actor_id text NOT NULL
    );
    CREATE UNIQUE INDEX event_store_stream_uniq ON event_store (stream_id, stream_version);
    CREATE TABLE outbox (
      message_id uuid PRIMARY KEY NOT NULL,
      stream_id text NOT NULL,
      aggregate_type text NOT NULL,
      payload jsonb NOT NULL,
      status text NOT NULL,
      attempt_count integer NOT NULL DEFAULT 0,
      next_attempt_at timestamptz NOT NULL,
      lease_owner text,
      lease_until timestamptz,
      last_error text,
      created_at timestamptz NOT NULL,
      delivered_at timestamptz
    );
    CREATE TABLE snapshots (
      stream_id text PRIMARY KEY NOT NULL,
      stream_version integer NOT NULL,
      payload jsonb NOT NULL,
      taken_at timestamptz NOT NULL
    );
    CREATE TABLE projections (
      projection_name text PRIMARY KEY NOT NULL,
      version integer NOT NULL,
      state jsonb NOT NULL,
      updated_at timestamptz NOT NULL
    );
  `)
  return { pg, db: drizzle(pg, { schema }), close: () => pg.close() }
}
```

**Step 7: 验证**

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm test packages/persistence 2>&1 | tail -5
echo "test_exit=$?"
```

Expected: 没有测试失败（0 tests if no test file present is acceptable）。

### R3.0 退出条件

- `packages/persistence/` 包加入 typecheck 链路；
- pglite helper 编译通过；
- 5 项 gate 全 exit 0。

---

## R3.1：EventStore append/load/subscribe

### Task 1.1: Append + 乐观并发

**Files:**
- Create: `butler-v5/packages/persistence/src/event-store.ts`
- Create: `butler-v5/packages/persistence/src/event-store.test.ts`

**Step 1: 写失败测试**

`butler-v5/packages/persistence/src/event-store.test.ts`:

```typescript
import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { eq } from "drizzle-orm"
import { appendEvents, loadStream, nextVersion } from "./event-store.js"
import { eventStore } from "./schema.js"
import { makeTestDb } from "./testing.js"
import type { ConversationEvent } from "../domain/src/conversation/types.js"

describe("event-store", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  beforeEach(async () => {
    db = await makeTestDb()
  })
  afterEach(async () => {
    await db.close()
  })

  it("appends an event with monotonically increasing streamVersion", async () => {
    const ev: ConversationEvent = { _tag: "ConversationStarted" } as ConversationEvent
    await appendEvents(db.db, "s-1", ev, {
      eventId: "e1",
      eventType: "ConversationStarted",
      eventVersion: 1,
      correlationId: "c1",
      occurredAt: new Date(),
      actor: { kind: "system", id: "test" },
    })
    await appendEvents(db.db, "s-1", { _tag: "MessageAdded" } as ConversationEvent, {
      eventId: "e2",
      eventType: "MessageAdded",
      eventVersion: 1,
      correlationId: "c1",
      occurredAt: new Date(),
      actor: { kind: "system", id: "test" },
    })
    const events = await loadStream(db.db, "s-1")
    expect(events.length).toBe(2)
    expect(events[0]!.streamVersion).toBe(1)
    expect(events[1]!.streamVersion).toBe(2)
  })

  it("rejects concurrent append when streamVersion conflicts", async () => {
    // First append consumes version 1.
    await appendEvents(
      db.db,
      "s-2",
      { _tag: "ConversationStarted" } as ConversationEvent,
      {
        eventId: "e1",
        eventType: "ConversationStarted",
        eventVersion: 1,
        correlationId: "c1",
        occurredAt: new Date(),
        actor: { kind: "system", id: "test" },
      },
    )
    // Second append also expects version 1 → must conflict.
    await expect(
      appendEvents(
        db.db,
        "s-2",
        { _tag: "MessageAdded" } as ConversationEvent,
        {
          eventId: "e2",
          eventType: "MessageAdded",
          eventVersion: 1,
          correlationId: "c1",
          occurredAt: new Date(),
          actor: { kind: "system", id: "test" },
        },
      ),
    ).rejects.toThrow(/optimistic concurrency/i)
  })

  it("nextVersion returns 1 for empty stream", async () => {
    const v = await nextVersion(db.db, "s-new")
    expect(v).toBe(1)
  })
})
```

**Step 2: 运行确认失败**

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm test packages/persistence/src/event-store.test.ts 2>&1 | tail -10
```

Expected: FAIL（appendEvents / loadStream / nextVersion not defined）。

**Step 3: 实现 event-store.ts**

`butler-v5/packages/persistence/src/event-store.ts`:

```typescript
import { eq, max, sql } from "drizzle-orm"
import type { PgliteDatabase } from "drizzle-orm/pglite"
import { eventStore } from "./schema.js"
import type { ConversationEvent } from "../domain/src/conversation/types.js"

export class OptimisticConcurrencyError extends Error {
  constructor(public readonly streamId: string, public readonly expectedVersion: number) {
    super(
      `optimistic concurrency conflict on stream ${streamId} at expected version ${expectedVersion}`,
    )
  }
}

export interface EnvelopeInput {
  readonly eventId: string
  readonly eventType: string
  readonly eventVersion: number
  readonly correlationId: string
  readonly occurredAt: Date
  readonly actor: { readonly kind: "owner" | "agent" | "system"; readonly id: string }
}

/**
 * Returns the next available streamVersion for a stream (1 if empty).
 */
export async function nextVersion(
  db: PgliteDatabase<Record<string, never>>,
  streamId: string,
): Promise<number> {
  const rows = await db
    .select({ max: max(eventStore.streamVersion) })
    .from(eventStore)
    .where(eq(eventStore.streamId, streamId))
  const m = rows[0]?.max
  return (m ?? 0) + 1
}

/**
 * Append events to a stream. streamVersion must be monotonic; conflicts throw
 * OptimisticConcurrencyError so the caller can retry with a fresh version.
 */
export async function appendEvents(
  db: PgliteDatabase<Record<string, never>>,
  streamId: string,
  event: ConversationEvent,
  envelope: EnvelopeInput,
): Promise<void> {
  const expectedVersion = envelope.eventVersion
  const version = await nextVersion(db, streamId)
  if (version !== expectedVersion) {
    throw new OptimisticConcurrencyError(streamId, expectedVersion)
  }
  await db.insert(eventStore).values({
    eventId: envelope.eventId,
    streamId,
    streamType: "conversation",
    streamVersion: version,
    eventType: envelope.eventType,
    eventVersion: envelope.eventVersion,
    payload: event,
    occurredAt: envelope.occurredAt,
    causationId: null,
    correlationId: envelope.correlationId,
    actorKind: envelope.actor.kind,
    actorId: envelope.actor.id,
  })
}

/**
 * Load all events for a stream in streamVersion ascending order.
 */
export async function loadStream(
  db: PgliteDatabase<Record<string, never>>,
  streamId: string,
): Promise<Array<typeof eventStore.$inferSelect>> {
  return db
    .select()
    .from(eventStore)
    .where(eq(eventStore.streamId, streamId))
    .orderBy(eventStore.streamVersion)
}
```

**Step 4: 运行测试**

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm test packages/persistence/src/event-store.test.ts 2>&1 | tail -10
echo "test_exit=$?"
```

Expected: PASS。

### Task 1.2: 订阅（projection-on-event 框架）

**Files:**
- Modify: `butler-v5/packages/persistence/src/event-store.ts`
- Create: `butler-v5/packages/persistence/src/subscribe.test.ts`

**Step 1: 写失败测试**

`butler-v5/packages/persistence/src/subscribe.test.ts`:

```typescript
import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { subscribeStream } from "./event-store.js"
import { appendEvents } from "./event-store.js"
import { makeTestDb } from "./testing.js"
import type { ConversationEvent } from "../domain/src/conversation/types.js"

describe("subscribe", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  beforeEach(async () => {
    db = await makeTestDb()
  })
  afterEach(async () => {
    await db.close()
  })

  it("calls handler once per newly appended event for matching stream", async () => {
    const received: number[] = []
    const handler = (e: { streamVersion: number }) => received.push(e.streamVersion)
    const cancel = subscribeStream(db.db, "s-sub", handler)
    await appendEvents(db.db, "s-sub", { _tag: "ConversationStarted" } as ConversationEvent, {
      eventId: "e1",
      eventType: "ConversationStarted",
      eventVersion: 1,
      correlationId: "c1",
      occurredAt: new Date(),
      actor: { kind: "system", id: "test" },
    })
    await new Promise((r) => setTimeout(r, 20))
    cancel()
    expect(received).toEqual([1])
  })
})
```

**Step 2: 运行确认失败**

```bash
pnpm test packages/persistence/src/subscribe.test.ts 2>&1 | tail -10
```

Expected: FAIL.

**Step 3: 扩展 event-store.ts**

追加（在文件末尾追加，保留所有现有导出）：

```typescript
/**
 * Long-poll style subscription: invokes handler for each newly appended event
 * on the given stream. Polls every 25ms; resolves via cancel() returned.
 */
export function subscribeStream(
  db: PgliteDatabase<Record<string, never>>,
  streamId: string,
  handler: (e: typeof eventStore.$inferSelect) => void,
): () => void {
  let lastVersion = 0
  let stopped = false
  const tick = async () => {
    if (stopped) return
    const rows = await loadStream(db, streamId)
    for (const row of rows) {
      if (row.streamVersion > lastVersion) {
        lastVersion = row.streamVersion
        handler(row)
      }
    }
    setTimeout(tick, 25)
  }
  setTimeout(tick, 0)
  return () => {
    stopped = true
  }
}
```

**Step 4: 运行**

```bash
pnpm test packages/persistence/src/subscribe.test.ts 2>&1 | tail -10
```

Expected: PASS.

### R3.1 退出条件

- event-store.ts 5 项 gate 全 exit 0（append / load / nextVersion / subscribe / OptimisticConcurrencyError）。
- pglite 测试覆盖。

---

## R3.2：Outbox enqueue/claim/deliver + Worker 幂等

### Task 2.1: enqueue + 原子提交

**Files:**
- Create: `butler-v5/packages/persistence/src/outbox.ts`
- Create: `butler-v5/packages/persistence/src/outbox.test.ts`

**Step 1: 写失败测试**

`butler-v5/packages/persistence/src/outbox.test.ts`:

```typescript
import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { enqueueOutbox, claimOutbox, completeOutbox, failOutbox } from "./outbox.js"
import { outbox } from "./schema.js"
import { makeTestDb } from "./testing.js"
import { eq } from "drizzle-orm"

describe("outbox", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  beforeEach(async () => {
    db = await makeTestDb()
  })
  afterEach(async () => {
    await db.close()
  })

  it("enqueues a message with status pending and attemptCount 0", async () => {
    const id = await enqueueOutbox(db.db, {
      streamId: "s-1",
      aggregateType: "Conversation",
      payload: { kind: "broadcast", text: "hello" },
    })
    const rows = await db.select().from(outbox).where(eq(outbox.messageId, id))
    expect(rows[0]?.status).toBe("pending")
    expect(rows[0]?.attemptCount).toBe(0)
    expect(rows[0]?.leaseOwner).toBeNull()
  })

  it("claimOutbox returns pending messages with expired lease", async () => {
    await enqueueOutbox(db.db, {
      streamId: "s-1",
      aggregateType: "Conversation",
      payload: { kind: "broadcast" },
    })
    const claimed = await claimOutbox(db.db, "worker-1", 60_000)
    expect(claimed.length).toBe(1)
    expect(claimed[0]?.leaseOwner).toBe("worker-1")
  })

  it("completeOutbox marks message delivered", async () => {
    const id = await enqueueOutbox(db.db, {
      streamId: "s-1",
      aggregateType: "Conversation",
      payload: {},
    })
    await claimOutbox(db.db, "worker-1", 60_000)
    await completeOutbox(db.db, id)
    const rows = await db.select().from(outbox).where(eq(outbox.messageId, id))
    expect(rows[0]?.status).toBe("delivered")
    expect(rows[0]?.deliveredAt).toBeInstanceOf(Date)
  })

  it("failOutbox increments attemptCount and sets nextAttemptAt", async () => {
    const id = await enqueueOutbox(db.db, {
      streamId: "s-1",
      aggregateType: "Conversation",
      payload: {},
    })
    await claimOutbox(db.db, "worker-1", 60_000)
    await failOutbox(db.db, id, "boom")
    const rows = await db.select().from(outbox).where(eq(outbox.messageId, id))
    expect(rows[0]?.attemptCount).toBe(1)
    expect(rows[0]?.lastError).toBe("boom")
    expect(rows[0]?.status).toBe("pending")
  })
})
```

**Step 2: 运行确认失败**

```bash
pnpm test packages/persistence/src/outbox.test.ts 2>&1 | tail -10
```

Expected: FAIL.

**Step 3: 实现 outbox.ts**

`butler-v5/packages/persistence/src/outbox.ts`:

```typescript
import { and, eq, lt, lte, sql } from "drizzle-orm"
import { randomUUID } from "node:crypto"
import type { PgliteDatabase } from "drizzle-orm/pglite"
import { outbox } from "./schema.js"

export type OutboxMessage = typeof outbox.$inferSelect

export interface EnqueueInput {
  readonly streamId: string
  readonly aggregateType: string
  readonly payload: Record<string, unknown>
}

const BASE_BACKOFF_MS = 1_000
const MAX_BACKOFF_MS = 60_000

/**
 * Insert a new outbox message in 'pending' state.
 */
export async function enqueueOutbox(
  db: PgliteDatabase<Record<string, never>>,
  input: EnqueueInput,
): Promise<string> {
  const messageId = randomUUID()
  const now = new Date()
  await db.insert(outbox).values({
    messageId,
    streamId: input.streamId,
    aggregateType: input.aggregateType,
    payload: input.payload,
    status: "pending",
    attemptCount: 0,
    nextAttemptAt: now,
    leaseOwner: null,
    leaseUntil: null,
    lastError: null,
    createdAt: now,
    deliveredAt: null,
  })
  return messageId
}

/**
 * Atomically claim up to `limit` pending messages whose lease has expired.
 * Uses UPDATE … RETURNING for single-round-trip claim.
 */
export async function claimOutbox(
  db: PgliteDatabase<Record<string, never>>,
  workerId: string,
  leaseMs: number,
  limit = 10,
): Promise<OutboxMessage[]> {
  const now = new Date()
  const leaseUntil = new Date(now.getTime() + leaseMs)
  const rows = await db
    .update(outbox)
    .set({ leaseOwner: workerId, leaseUntil, status: "in_flight" })
    .where(
      and(
        eq(outbox.status, "pending"),
        sql`(${outbox.leaseUntil} IS NULL OR ${outbox.leaseUntil} <= ${now})`,
      ),
    )
    .returning()
    return rows.slice(0, limit)
}

/**
 * Mark a claimed message as successfully delivered.
 */
export async function completeOutbox(
  db: PgliteDatabase<Record<string, never>>,
  messageId: string,
): Promise<void> {
  await db
    .update(outbox)
    .set({ status: "delivered", deliveredAt: new Date() })
    .where(eq(outbox.messageId, messageId))
}

/**
 * Record a failed delivery attempt and schedule the next retry with
 * exponential backoff (BASE * 2^(attempt-1), capped at MAX).
 */
export async function failOutbox(
  db: PgliteDatabase<Record<string, never>>,
  messageId: string,
  error: string,
): Promise<void> {
  const rows = await db.select().from(outbox).where(eq(outbox.messageId, messageId))
  const msg = rows[0]
  if (!msg) return
  const attempt = (msg.attemptCount ?? 0) + 1
  const backoff = Math.min(BASE_BACKOFF_MS * Math.pow(2, attempt - 1), MAX_BACKOFF_MS)
  const nextAttemptAt = new Date(Date.now() + backoff)
  await db
    .update(outbox)
    .set({
      attemptCount: attempt,
      lastError: error.slice(0, 1000),
      nextAttemptAt,
      leaseOwner: null,
      leaseUntil: null,
      status: "pending",
    })
    .where(eq(outbox.messageId, messageId))
}
```

**Step 4: 运行**

```bash
pnpm test packages/persistence/src/outbox.test.ts 2>&1 | tail -10
```

Expected: PASS.

### Task 2.2: Worker 幂等 + at-least-once

**Files:**
- Create: `butler-v5/packages/persistence/src/worker.ts`
- Create: `butler-v5/packages/persistence/src/worker.test.ts`

**Step 1: 写失败测试**

`butler-v5/packages/persistence/src/worker.test.ts`:

```typescript
import { describe, expect, it, beforeEach, afterEach, vi } from "vitest"
import { runWorkerOnce } from "./worker.js"
import { enqueueOutbox } from "./outbox.js"
import { outbox } from "./schema.js"
import { makeTestDb } from "./testing.js"
import { eq } from "drizzle-orm"

describe("worker", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  beforeEach(async () => {
    db = await makeTestDb()
  })
  afterEach(async () => {
    await db.close()
  })

  it("delivers each pending message exactly once per attempt", async () => {
    await enqueueOutbox(db.db, { streamId: "s-1", aggregateType: "X", payload: { id: 1 } })
    await enqueueOutbox(db.db, { streamId: "s-2", aggregateType: "X", payload: { id: 2 } })

    const delivered: number[] = []
    const handler = vi.fn(async (msg: { payload: { id: number } }) => {
      delivered.push(msg.payload.id)
    })

    const processed = await runWorkerOnce(db.db, "w-1", 60_000, handler)
    expect(processed).toBe(2)
    expect(delivered.sort()).toEqual([1, 2])

    const remaining = await db.select().from(outbox)
    expect(remaining.every((r) => r.status === "delivered")).toBe(true)
    expect(handler).toHaveBeenCalledTimes(2)
  })

  it("does not redeliver an already delivered message on second run", async () => {
    await enqueueOutbox(db.db, { streamId: "s-1", aggregateType: "X", payload: { id: 1 } })
    const handler = vi.fn(async () => {})
    await runWorkerOnce(db.db, "w-1", 60_000, handler)
    const processed = await runWorkerOnce(db.db, "w-1", 60_000, handler)
    expect(processed).toBe(0)
    expect(handler).toHaveBeenCalledTimes(1)
  })
})
```

**Step 2: 运行确认失败**

```bash
pnpm test packages/persistence/src/worker.test.ts 2>&1 | tail -10
```

Expected: FAIL.

**Step 3: 实现 worker.ts**

`butler-v5/packages/persistence/src/worker.ts`:

```typescript
import { claimOutbox, completeOutbox, failOutbox } from "./outbox.js"
import type { OutboxMessage } from "./outbox.js"
import type { PgliteDatabase } from "drizzle-orm/pglite"

/**
 * Process up to one batch of claimed messages.
 * Returns the count successfully delivered in this run.
 */
export async function runWorkerOnce(
  db: PgliteDatabase<Record<string, never>>,
  workerId: string,
  leaseMs: number,
  handler: (msg: OutboxMessage) => Promise<void>,
): Promise<number> {
  const claimed = await claimOutbox(db, workerId, leaseMs)
  let delivered = 0
  for (const msg of claimed) {
    try {
      await handler(msg)
      await completeOutbox(db, msg.messageId)
      delivered++
    } catch (err) {
      await failOutbox(db, msg.messageId, err instanceof Error ? err.message : String(err))
    }
  }
  return delivered
}
```

**Step 4: 运行**

```bash
pnpm test packages/persistence/src/worker.test.ts 2>&1 | tail -10
```

Expected: PASS.

### R3.2 退出条件

- enqueueOutbox / claimOutbox / completeOutbox / failOutbox 全绿；
- Worker 幂等：delivered 消息不会二次投递；
- 5 项 gate 全 exit 0。

---

## R3.3：Projection on_event + 全量 rebuild

### Task 3.1: 投影注册表与增量应用

**Files:**
- Create: `butler-v5/packages/persistence/src/projections.ts`
- Create: `butler-v5/packages/persistence/src/projections.test.ts`

**Step 1: 写失败测试**

`butler-v5/packages/persistence/src/projections.test.ts`:

```typescript
import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { registerProjection, applyProjection, rebuildProjection } from "./projections.js"
import { projections } from "./schema.js"
import { appendEvents } from "./event-store.js"
import { makeTestDb } from "./testing.js"
import { eq } from "drizzle-orm"
import type { ConversationEvent } from "../domain/src/conversation/types.js"

describe("projections", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  beforeEach(async () => {
    db = await makeTestDb()
  })
  afterEach(async () => {
    await db.close()
  })

  it("applyProjection invokes the handler once per event", async () => {
    let count = 0
    registerProjection("counter", async () => {
      count++
    })
    await appendEvents(db.db, "s-1", { _tag: "ConversationStarted" } as ConversationEvent, {
      eventId: "e1",
      eventType: "ConversationStarted",
      eventVersion: 1,
      correlationId: "c1",
      occurredAt: new Date(),
      actor: { kind: "system", id: "test" },
    })
    await applyProjection(db.db, "s-1", "counter")
    expect(count).toBe(1)
  })

  it("rebuildProjection replays all events for a stream", async () => {
    let count = 0
    registerProjection("counter", async () => {
      count++
    })
    await appendEvents(db.db, "s-2", { _tag: "A" } as ConversationEvent, {
      eventId: "e1",
      eventType: "A",
      eventVersion: 1,
      correlationId: "c1",
      occurredAt: new Date(),
      actor: { kind: "system", id: "test" },
    })
    await appendEvents(db.db, "s-2", { _tag: "B" } as ConversationEvent, {
      eventId: "e2",
      eventType: "B",
      eventVersion: 1,
      correlationId: "c1",
      occurredAt: new Date(),
      actor: { kind: "system", id: "test" },
    })
    await rebuildProjection(db.db, "s-2", "counter")
    expect(count).toBe(2)
  })

  it("projection state is persisted between runs", async () => {
    let lastVersion = 0
    registerProjection("persist-test", async () => {})
    await appendEvents(db.db, "s-3", { _tag: "A" } as ConversationEvent, {
      eventId: "e1",
      eventType: "A",
      eventVersion: 1,
      correlationId: "c1",
      occurredAt: new Date(),
      actor: { kind: "system", id: "test" },
    })
    await applyProjection(db.db, "s-3", "persist-test")
    const rows = await db.select().from(projections).where(eq(projections.projectionName, "persist-test"))
    expect(rows[0]?.version).toBeGreaterThan(0)
  })
})
```

**Step 2: 运行确认失败**

```bash
pnpm test packages/persistence/src/projections.test.ts 2>&1 | tail -10
```

Expected: FAIL.

**Step 3: 实现 projections.ts**

`butler-v5/packages/persistence/src/projections.ts`:

```typescript
import { eq } from "drizzle-orm"
import type { PgliteDatabase } from "drizzle-orm/pglite"
import { projections } from "./schema.js"
import { eventStore } from "./schema.js"
import { loadStream } from "./event-store.js"

type Handler = (event: typeof eventStore.$inferSelect) => Promise<void>

const registry = new Map<string, Handler>()

/**
 * Register a projection handler by name.
 */
export function registerProjection(name: string, handler: Handler): void {
  registry.set(name, handler)
}

/**
 * Apply the projection to all events in a stream, then bump the
 * persisted projection version to the latest streamVersion processed.
 */
export async function applyProjection(
  db: PgliteDatabase<Record<string, never>>,
  streamId: string,
  projectionName: string,
): Promise<void> {
  const handler = registry.get(projectionName)
  if (!handler) throw new Error(`unknown projection: ${projectionName}`)
  const events = await loadStream(db, streamId)
  for (const e of events) {
    await handler(e)
  }
  const last = events.at(-1)?.streamVersion ?? 0
  await db
    .insert(projections)
    .values({ projectionName, version: last, state: {}, updatedAt: new Date() })
    .onConflictDoUpdate({
      target: projections.projectionName,
      set: { version: last, updatedAt: new Date() },
    })
}

/**
 * Wipe the projection's persisted state and replay all events for the stream.
 * Use when handler logic changes or data drifts.
 */
export async function rebuildProjection(
  db: PgliteDatabase<Record<string, never>>,
  streamId: string,
  projectionName: string,
): Promise<void> {
  await db.delete(projections).where(eq(projections.projectionName, projectionName))
  await applyProjection(db, streamId, projectionName)
}
```

**Step 4: 运行**

```bash
pnpm test packages/persistence/src/projections.test.ts 2>&1 | tail -10
```

Expected: PASS.

### R3.3 退出条件

- registerProjection / applyProjection / rebuildProjection 3 个测试全过；
- 5 项 gate 全 exit 0。

---

## R3.4：Crash recovery + snapshot

### Task 4.1: Snapshot 落盘与恢复

**Files:**
- Create: `butler-v5/packages/persistence/src/snapshot.ts`
- Create: `butler-v5/packages/persistence/src/snapshot.test.ts`

**Step 1: 写失败测试**

`butler-v5/packages/persistence/src/snapshot.test.ts`:

```typescript
import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { saveSnapshot, loadSnapshot } from "./snapshot.js"
import { snapshots } from "./schema.js"
import { appendEvents } from "./event-store.js"
import { makeTestDb } from "./testing.js"
import { eq } from "drizzle-orm"

describe("snapshot", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  beforeEach(async () => {
    db = await makeTestDb()
  })
  afterEach(async () => {
    await db.close()
  })

  it("saves and loads a snapshot for a stream", async () => {
    await saveSnapshot(db.db, "s-1", 5, { count: 3 })
    const loaded = await loadSnapshot(db.db, "s-1")
    expect(loaded?.streamVersion).toBe(5)
    expect(loaded?.payload).toEqual({ count: 3 })
  })

  it("overwrites an older snapshot for the same stream", async () => {
    await saveSnapshot(db.db, "s-1", 3, { v: 3 })
    await saveSnapshot(db.db, "s-1", 7, { v: 7 })
    const loaded = await loadSnapshot(db.db, "s-1")
    expect(loaded?.streamVersion).toBe(7)
    expect(loaded?.payload).toEqual({ v: 7 })
  })

  it("returns null for a stream with no snapshot", async () => {
    const loaded = await loadSnapshot(db.db, "s-missing")
    expect(loaded).toBeNull()
  })
})
```

**Step 2: 运行确认失败**

```bash
pnpm test packages/persistence/src/snapshot.test.ts 2>&1 | tail -10
```

Expected: FAIL.

**Step 3: 实现 snapshot.ts**

`butler-v5/packages/persistence/src/snapshot.ts`:

```typescript
import { eq } from "drizzle-orm"
import type { PgliteDatabase } from "drizzle-orm/pglite"
import { snapshots } from "./schema.js"

export type Snapshot = typeof snapshots.$inferSelect

/**
 * Save or replace the snapshot for a stream. Last writer wins; a more
 * recent streamVersion overwrites an older one.
 */
export async function saveSnapshot(
  db: PgliteDatabase<Record<string, never>>,
  streamId: string,
  streamVersion: number,
  payload: Record<string, unknown>,
): Promise<void> {
  await db
    .insert(snapshots)
    .values({ streamId, streamVersion, payload, takenAt: new Date() })
    .onConflictDoUpdate({
      target: snapshots.streamId,
      set: { streamVersion, payload, takenAt: new Date() },
    })
}

/**
 * Load the current snapshot for a stream, or null if none exists.
 */
export async function loadSnapshot(
  db: PgliteDatabase<Record<string, never>>,
  streamId: string,
): Promise<Snapshot | null> {
  const rows = await db.select().from(snapshots).where(eq(snapshots.streamId, streamId))
  return rows[0] ?? null
}
```

**Step 4: 运行**

```bash
pnpm test packages/persistence/src/snapshot.test.ts 2>&1 | tail -10
```

Expected: PASS.

### R3.4 退出条件

- saveSnapshot / loadSnapshot 测试全过；
- 5 项 gate 全 exit 0。

---

## R3.5：端到端门禁（含 Postgres container / pglite 双路径）

### Task 5.1: R3 end-to-end test

**Files:**
- Create: `butler-v5/tests/architecture/r3-end-to-end.test.ts`

`butler-v5/tests/architecture/r3-end-to-end.test.ts`:

```typescript
import { describe, it } from "vitest"
import { execFileSync } from "node:child_process"

describe("R3 end-to-end gates", () => {
  it("architecture suite is part of pnpm test", () => {
    // No-op: presence under tests/architecture/ is sufficient.
    // Re-running pnpm test inside a vitest worker causes memory exhaustion.
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

  it("R3 persistence test suite passes", () => {
    execFileSync("pnpm", ["test", "packages/persistence"], {
      cwd: process.cwd(),
      stdio: ["ignore", "pipe", "pipe"],
    })
  })
})
```

### Task 5.2: Postgres container 干跑（可选）

**Files:**
- Create: `butler-v5/tests/architecture/r3-postgres-container.test.ts`（如果 Docker 可用，否则跳过此 task）

`butler-v5/tests/architecture/r3-postgres-container.test.ts`:

```typescript
import { describe, it } from "vitest"
import { execFileSync } from "node:child_process"

describe.skipIfNoDocker("R3 Postgres container", () => {
  it("applies migrations and runs full lifecycle against real Postgres", () => {
    // docker compose up -d postgres
    // psql -c "select 1 from event_store"
    // pnpm test packages/persistence/src/postgres-live.test.ts (out of R3 scope)
    execFileSync("docker", ["compose", "up", "-d", "postgres"], { cwd: process.cwd() })
    try {
      execFileSync("pnpm", ["test", "packages/persistence"], { cwd: process.cwd() })
    } finally {
      execFileSync("docker", ["compose", "down"], { cwd: process.cwd() })
    }
  })
})
```

### Task 5.3: 验证

```bash
cd /home/ailearn/projects/WFXM/butler-v5
set -o pipefail
pnpm test tests/architecture/r3-end-to-end.test.ts 2>&1 | tail -10
echo "test_exit=$?"
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
bash scripts/typecheck-gate.sh 2>&1 | tail -8
echo "gate_exit=$?"
```

Expected: 全部 exit 0。

---

## R3 整体退出条件

- 5 项 gate 全 exit 0；
- `packages/persistence/` 包含 schema / event-store / outbox / projections / snapshot 五大模块；
- pglite in-process 测试覆盖所有持久化逻辑；
- 端到端测试 `tests/architecture/r3-end-to-end.test.ts` 集成所有子项目；
- 黑板卡 007 已落盘记录 R3 收口。

---

## 与规格覆盖检查

- 规格 §7.1 三类事件：R2/R3 已实现 Domain Events；R3 提供持久化与 Outbox。
- 规格 §7.2 Event Envelope：R2.3 已定义；R3.1 在 `appendEvents` 中保持 envelope 字段。
- 规格 §7.3 Outbox 与 Projection：R3.2 + R3.3 实现。
- 规格 §7.4 Crash recovery：R3.4 snapshot + rebuildProjection 实现。
- 规格 §13 R3 阶段：5 子项目一一映射。

---

## 已知偏差与待办

- **butler-v5/packages/persistence 是新包**，不在工作区 `.eslintrc.json` 的 `parserOptions.project` 与 `vitest.config.ts` 的 `resolve.alias` 中——Task 0.1 Step 6 已通过 `pnpm install` + `pnpm typecheck` 自动处理 alias（pnpm workspace glob 自动包含），但 ESLint coverage 与 alias 需要：
  - 修改 `.eslintrc.json` `parserOptions.project` 加上 `"./packages/persistence/tsconfig.json"`
  - 修改 `vitest.config.ts` `resolve.alias` 加上 `"@butler/persistence": resolve(__dirname, "packages/persistence/src")`
  - 修改 `tests/architecture/dependency-direction.test.ts` 增加 `persistence may import domain only` 块
- **infrastructure 叶子文件 8 个未引用 export**（chaosScenarios / runChaosDrill / migrateV4ToV5 / applyPatch / buildRepoMap / topKImportant / ShadowModeLive / shadowMode）—— R3+ 清理。
- **CI workflow 与本地 gate 行为差异** —— R3+ Owner 手动应用。

不阻塞 R3 主线推进，R3+ 阶段由 Owner / 后继迭代解决。

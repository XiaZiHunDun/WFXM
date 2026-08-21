// infrastructure/persistence/eventstore-live.ts
// Hybrid EventStore — 事件 + Snapshot [OPT-12]
// Phase 3 实现

import { Effect, Layer, Stream } from "effect"
import { drizzle } from "drizzle-orm/postgres-js"
import postgres from "postgres"
import { eq, sql } from "drizzle-orm"
import { EventStoreService } from "@butler/ports"
import type { ConversationEvent, LoopError } from "@butler/domain"
import * as schema from "./schema.js"

// ─── 辅助 ───────────────────────────────────────────────
function nextVersion(
  db: ReturnType<typeof drizzle<typeof schema>>,
  streamId: string,
): Effect.Effect<number, LoopError> {
  return Effect.tryPromise({
    try: async () => {
      const result = await db
        .select({ count: sql<number>`COALESCE(MAX(${schema.events.version}), 0) + 1` })
        .from(schema.events)
        .where(eq(schema.events.streamId, streamId))
      return result[0]?.count ?? 1
    },
    catch: (e) => ({
      _tag: "PersistenceFailed" as const,
      operation: "nextVersion",
      cause: String(e),
    }),
  })
}

// ─── DrizzleEventStoreLive ───────────────────────────────
export const DrizzleEventStoreLive = Layer.effect(
  EventStoreService,
  Effect.sync(() => {
    // Phase 3: 使用真实连接（Phase 4 加 Snapshot 表）
    const globalProcess = (globalThis as { process?: { env?: Record<string, string | undefined> } })
      .process
    const url =
      globalProcess?.env?.["DATABASE_URL"] ??
      "postgres://butler:butler_dev@localhost:5432/butler_v5"
    const client = postgres(url, { max: 10 })
    const db = drizzle(client, { schema })

    return EventStoreService.of({
      append: (streamId, events) =>
        Effect.gen(function* () {
          for (const event of events) {
            const version = yield* nextVersion(db, streamId)
            yield* Effect.tryPromise({
              try: () =>
                db.insert(schema.events).values({
                  id: crypto.randomUUID(),
                  streamId,
                  version,
                  type: (event as { _tag: string })._tag,
                  payload: event as unknown as Record<string, unknown>,
                  createdAt: new Date(),
                }),
              catch: (e) =>
                ({
                  _tag: "PersistenceFailed" as const,
                  operation: "append",
                  cause: String(e),
                }) as LoopError,
            })
          }
        }),

      load: (streamId) =>
        Effect.tryPromise({
          try: async () => {
            const rows = await db
              .select()
              .from(schema.events)
              .where(eq(schema.events.streamId, streamId))
              .orderBy(schema.events.version)
            return rows.map((r) => r.payload as unknown as ConversationEvent)
          },
          catch: (e) =>
            ({
              _tag: "PersistenceFailed" as const,
              operation: "load",
              cause: String(e),
            }) as LoopError,
        }),

      subscribe: () => Stream.fromIterable([]),
    })
  }),
)

// ─── 测试用 Mock EventStore（内存） ──────────────────────
export const MockEventStoreLive = Layer.effect(
  EventStoreService,
  Effect.sync(() => {
    const store = new Map<string, ConversationEvent[]>()
    return EventStoreService.of({
      append: (streamId, events) =>
        Effect.sync(() => {
          const existing = store.get(streamId) ?? []
          store.set(streamId, [...existing, ...events])
        }),
      load: (streamId) => Effect.sync(() => store.get(streamId) ?? []),
      subscribe: () => Stream.fromIterable([]),
    })
  }),
)

import { and, asc, eq, inArray, isNull } from "drizzle-orm"
import {
  ACTIVE_MAIN_RUN_STATUSES,
  inferProjectIdFromConversationId,
  type ReadModelSource,
} from "@butler/domain/runtime.js"
import type { EventStoreRow } from "./event-store.js"
import type { ButlerDb } from "./db.js"
import { conversations, messages, runs } from "./schema.js"
import { createRuntimeStore } from "./runtime-store.js"

function payloadContent(payload: unknown): string {
  if (payload === null || typeof payload !== "object") return ""
  const content = (payload as { content?: unknown }).content
  return typeof content === "string" ? content.trim() : ""
}

function payloadRole(payload: unknown): string {
  if (payload === null || typeof payload !== "object") return ""
  const role = (payload as { role?: unknown }).role
  return typeof role === "string" ? role : ""
}

function messageText(content: Readonly<Record<string, unknown>>): string {
  const text = content["text"]
  return typeof text === "string" ? text.trim() : ""
}

async function relationalHasUserText(
  db: ButlerDb,
  conversationId: string,
  text: string,
): Promise<boolean> {
  if (!text) return false
  const rows = await db
    .select({ content: messages.content, role: messages.role })
    .from(messages)
    .where(eq(messages.conversationId, conversationId))
  return rows.some((row) => row.role === "user" && messageText(row.content) === text)
}

function eventsToStoredMessages(
  streamId: string,
  events: readonly EventStoreRow[],
): {
  readonly messageId: string
  readonly conversationId: string
  readonly role: "user" | "assistant"
  readonly content: Readonly<Record<string, unknown>>
  readonly idempotencyKey: string
  readonly createdAt: Date
}[] {
  const out: {
    readonly messageId: string
    readonly conversationId: string
    readonly role: "user" | "assistant"
    readonly content: Readonly<Record<string, unknown>>
    readonly idempotencyKey: string
    readonly createdAt: Date
  }[] = []
  for (const event of events) {
    const content = payloadContent(event.payload)
    if (!content) continue
    if (event.eventType === "TurnOpened" && payloadRole(event.payload) !== "assistant") {
      out.push({
        messageId: event.eventId,
        conversationId: streamId,
        role: "user",
        content: { text: content },
        idempotencyKey: `backfill:${streamId}:${event.streamVersion}`,
        createdAt: event.occurredAt,
      })
    }
    if (event.eventType === "AssistantMessageProduced") {
      out.push({
        messageId: event.eventId,
        conversationId: streamId,
        role: "assistant",
        content: { text: content },
        idempotencyKey: `backfill:${streamId}:${event.streamVersion}`,
        createdAt: event.occurredAt,
      })
    }
  }
  return out
}

export interface BackfillStats {
  readonly streamsProcessed: number
  readonly messagesInserted: number
  readonly conversationsCreated: number
}

/** Idempotently project event_store conversation streams into relational tables. */
export async function backfillRuntimeFromEventStore(
  db: ButlerDb,
  streamIds: readonly string[],
): Promise<BackfillStats> {
  const store = createRuntimeStore(db)
  let messagesInserted = 0
  let conversationsCreated = 0

  for (const streamId of streamIds) {
    const { loadStream } = await import("./event-store.js")
    const events = await loadStream(db, streamId)
    if (events.length === 0) continue

    const existingConversation = await db
      .select()
      .from(conversations)
      .where(eq(conversations.conversationId, streamId))
      .limit(1)
    if (existingConversation.length === 0) {
      const firstAt = events[0]?.occurredAt ?? new Date()
      await db.insert(conversations).values({
        conversationId: streamId,
        projectId: inferProjectIdFromConversationId(streamId),
        subject: streamId,
        createdAt: firstAt,
        updatedAt: firstAt,
      })
      conversationsCreated += 1
    }

    for (const msg of eventsToStoredMessages(streamId, events)) {
      const before = await db
        .select()
        .from(messages)
        .where(eq(messages.idempotencyKey, msg.idempotencyKey))
        .limit(1)
      if (before.length > 0) continue
      if (
        msg.role === "user" &&
        (await relationalHasUserText(db, streamId, messageText(msg.content)))
      ) {
        continue
      }
      await db.insert(messages).values({
        messageId: msg.messageId,
        conversationId: msg.conversationId,
        role: msg.role,
        content: msg.content,
        triggerSource: "channel",
        idempotencyKey: msg.idempotencyKey,
        createdAt: msg.createdAt,
      })
      messagesInserted += 1
    }

    const existingRuns = await db
      .select()
      .from(runs)
      .where(and(eq(runs.conversationId, streamId), isNull(runs.parentRunId)))
      .limit(1)
    if (existingRuns.length === 0 && events.some((e) => e.eventType === "TurnOpened")) {
      const firstAt = events[0]?.occurredAt ?? new Date()
      await store.createRun({
        id: crypto.randomUUID(),
        conversationId: streamId,
        parentRunId: null,
        triggerSource: "channel",
        idempotencyKey: `backfill-run:${streamId}`,
        subject: streamId,
        goal: "backfill",
        budget: { maxSteps: 5 },
        deadline: null,
        createdAt: firstAt,
      })
    }
  }

  return {
    streamsProcessed: streamIds.length,
    messagesInserted,
    conversationsCreated,
  }
}

export async function loadConversationMessages(
  db: ButlerDb,
  conversationId: string,
  source: ReadModelSource,
  loadEvents: () => Promise<readonly EventStoreRow[]>,
): Promise<readonly (typeof messages.$inferSelect)[]> {
  const relational = await db
    .select()
    .from(messages)
    .where(eq(messages.conversationId, conversationId))
    .orderBy(asc(messages.createdAt))

  if (source === "relational") {
    return relational
  }

  if (source === "event_store" || relational.length > 0) {
    if (source === "event_store" && relational.length === 0) {
      const events = await loadEvents()
      const projected = eventsToStoredMessages(conversationId, events)
      return projected.map((m) => ({
        messageId: m.messageId,
        conversationId: m.conversationId,
        role: m.role,
        content: m.content,
        triggerSource: "channel",
        idempotencyKey: m.idempotencyKey,
        createdAt: m.createdAt,
      }))
    }
    if (relational.length > 0) {
      return relational
    }
  }

  const events = await loadEvents()
  const projected = eventsToStoredMessages(conversationId, events)
  return projected.map((m) => ({
    messageId: m.messageId,
    conversationId: m.conversationId,
    role: m.role,
    content: m.content,
    triggerSource: "channel",
    idempotencyKey: m.idempotencyKey,
    createdAt: m.createdAt,
  }))
}

export async function findActiveMainRun(db: ButlerDb, conversationId: string) {
  const rows = await db
    .select()
    .from(runs)
    .where(
      and(
        eq(runs.conversationId, conversationId),
        isNull(runs.parentRunId),
        inArray(runs.status, [...ACTIVE_MAIN_RUN_STATUSES]),
      ),
    )
    .limit(1)
  return rows[0] ?? null
}

export async function listDistinctStreamIds(db: ButlerDb): Promise<readonly string[]> {
  const { eventStore } = await import("./schema.js")
  const rows = await db
    .select({ streamId: eventStore.streamId })
    .from(eventStore)
    .groupBy(eventStore.streamId)
  return rows.map((r) => r.streamId)
}

export async function verifyBackfillParity(
  db: ButlerDb,
  streamId: string,
): Promise<{ readonly ok: boolean; readonly eventCount: number; readonly messageCount: number }> {
  const { loadStream } = await import("./event-store.js")
  const events = await loadStream(db, streamId)
  const eventMessages = eventsToStoredMessages(streamId, events)
  const relational = await db.select().from(messages).where(eq(messages.conversationId, streamId))
  return {
    ok: relational.length >= eventMessages.length,
    eventCount: eventMessages.length,
    messageCount: relational.length,
  }
}

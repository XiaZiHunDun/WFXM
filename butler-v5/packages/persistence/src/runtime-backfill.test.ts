import { describe, expect, it } from "vitest"
import { eq } from "drizzle-orm"
import { appendEvents } from "./event-store.js"
import {
  backfillRuntimeFromEventStore,
  loadConversationMessages,
  verifyBackfillParity,
} from "./runtime-backfill.js"
import { createRuntimeStore } from "./runtime-store.js"
import { messages } from "./schema.js"
import { makeTestDb } from "./testing.js"

describe("runtime backfill", () => {
  it("projects TurnOpened and AssistantMessageProduced into messages", async () => {
    const db = await makeTestDb()
    const streamId = "c-backfill-1"
    try {
      await appendEvents(
        db,
        streamId,
        { role: "user", content: "hello" },
        {
          eventId: crypto.randomUUID(),
          eventType: "TurnOpened",
          eventVersion: 1,
          correlationId: "c1",
          occurredAt: new Date("2026-08-20T00:00:00Z"),
          actor: { kind: "owner", id: "u1" },
        },
      )
      await appendEvents(
        db,
        streamId,
        { content: "hi back" },
        {
          eventId: crypto.randomUUID(),
          eventType: "AssistantMessageProduced",
          eventVersion: 2,
          correlationId: "c2",
          occurredAt: new Date("2026-08-20T00:00:01Z"),
          actor: { kind: "agent", id: "agent" },
        },
      )

      const stats = await backfillRuntimeFromEventStore(db, [streamId])
      expect(stats.messagesInserted).toBe(2)
      expect(stats.conversationsCreated).toBe(1)

      const parity = await verifyBackfillParity(db, streamId)
      expect(parity.ok).toBe(true)

      const hybrid = await loadConversationMessages(db, streamId, "hybrid", async () => [])
      expect(hybrid).toHaveLength(2)
    } finally {
      await db.close()
    }
  })

  it("is idempotent on repeated backfill", async () => {
    const db = await makeTestDb()
    const streamId = "c-backfill-2"
    try {
      await appendEvents(
        db,
        streamId,
        { role: "user", content: "one" },
        {
          eventId: crypto.randomUUID(),
          eventType: "TurnOpened",
          eventVersion: 1,
          correlationId: "c1",
          occurredAt: new Date(),
          actor: { kind: "owner", id: "u1" },
        },
      )
      const first = await backfillRuntimeFromEventStore(db, [streamId])
      const second = await backfillRuntimeFromEventStore(db, [streamId])
      expect(first.messagesInserted).toBe(1)
      expect(second.messagesInserted).toBe(0)
    } finally {
      await db.close()
    }
  })

  it("does not backfill TurnOpened user text already in relational messages", async () => {
    const db = await makeTestDb()
    const streamId = "c-backfill-dedup"
    const store = createRuntimeStore(db)
    try {
      await store.createConversationWithUserMessage({
        conversationId: streamId,
        messageId: crypto.randomUUID(),
        subject: "u1",
        content: { text: "hello from run engine" },
        triggerSource: "channel",
        idempotencyKey: "inbound-1",
        createdAt: new Date("2026-08-20T00:00:00Z"),
      })
      await appendEvents(
        db,
        streamId,
        { role: "user", content: "hello from run engine" },
        {
          eventId: crypto.randomUUID(),
          eventType: "TurnOpened",
          eventVersion: 1,
          correlationId: "c1",
          occurredAt: new Date("2026-08-20T00:00:01Z"),
          actor: { kind: "owner", id: "u1" },
        },
      )
      const stats = await backfillRuntimeFromEventStore(db, [streamId])
      expect(stats.messagesInserted).toBe(0)
      const rows = await db.select().from(messages).where(eq(messages.conversationId, streamId))
      expect(rows.filter((r) => r.role === "user")).toHaveLength(1)
    } finally {
      await db.close()
    }
  })
})

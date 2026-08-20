import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { eq } from "drizzle-orm"
import {
  appendEventAndEnqueueOutbox,
  appendEvents,
  appendEventsWithRetry,
  loadStream,
  nextVersion,
  OptimisticConcurrencyError,
} from "./event-store.js"
import { outbox } from "./schema.js"
import { makeTestDb } from "./testing.js"

describe("event-store", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  beforeEach(async () => {
    db = await makeTestDb()
  })
  afterEach(async () => {
    await db.close()
  })

  it("appends events with monotonically increasing streamVersion", async () => {
    await appendEvents(
      db.db,
      "s-1",
      { _tag: "ConversationStarted" },
      {
        eventId: "e1",
        eventType: "ConversationStarted",
        eventVersion: 1,
        correlationId: "c1",
        occurredAt: new Date(),
        actor: { kind: "system", id: "test" },
      },
    )
    await appendEvents(
      db.db,
      "s-1",
      { _tag: "MessageAdded" },
      {
        eventId: "e2",
        eventType: "MessageAdded",
        eventVersion: 2,
        correlationId: "c1",
        occurredAt: new Date(),
        actor: { kind: "system", id: "test" },
      },
    )
    const events = await loadStream(db.db, "s-1")
    expect(events.length).toBe(2)
    expect(events[0]?.streamVersion).toBe(1)
    expect(events[1]?.streamVersion).toBe(2)
  })

  it("rejects concurrent append when expectedVersion conflicts", async () => {
    await appendEvents(
      db.db,
      "s-2",
      { _tag: "ConversationStarted" },
      {
        eventId: "e1",
        eventType: "ConversationStarted",
        eventVersion: 1,
        correlationId: "c1",
        occurredAt: new Date(),
        actor: { kind: "system", id: "test" },
      },
    )
    await expect(
      appendEvents(
        db.db,
        "s-2",
        { _tag: "MessageAdded" },
        {
          eventId: "e2",
          eventType: "MessageAdded",
          eventVersion: 1,
          correlationId: "c1",
          occurredAt: new Date(),
          actor: { kind: "system", id: "test" },
        },
      ),
    ).rejects.toThrow(OptimisticConcurrencyError)
  })

  it("nextVersion returns 1 for empty stream", async () => {
    const v = await nextVersion(db.db, "s-new")
    expect(v).toBe(1)
  })

  it("appendEventsWithRetry succeeds under concurrent appends", async () => {
    const base = {
      correlationId: "c-conc",
      occurredAt: new Date(),
      actor: { kind: "system" as const, id: "test" },
    }
    await Promise.all([
      appendEventsWithRetry(
        db.db,
        "s-conc",
        { _tag: "A" },
        { eventId: "e-a", eventType: "MessageAdded", ...base },
      ),
      appendEventsWithRetry(
        db.db,
        "s-conc",
        { _tag: "B" },
        { eventId: "e-b", eventType: "MessageAdded", ...base },
      ),
    ])
    const events = await loadStream(db.db, "s-conc")
    expect(events.length).toBe(2)
    expect(events.map((e) => e.streamVersion).sort()).toEqual([1, 2])
  })

  it("appendEventAndEnqueueOutbox writes event and outbox atomically", async () => {
    const messageId = await appendEventAndEnqueueOutbox(
      db.db,
      "s-atomic",
      { _tag: "ChildRunCreated" },
      {
        eventId: "e-delegate",
        eventType: "ChildRunCreated",
        correlationId: "c1",
        occurredAt: new Date(),
        actor: { kind: "agent", id: "kernel" },
      },
      {
        streamId: "s-atomic",
        aggregateType: "Delegate",
        payload: { childConversationId: "child-1" },
      },
    )
    const events = await loadStream(db.db, "s-atomic")
    const rows = await db.select().from(outbox).where(eq(outbox.messageId, messageId))
    expect(events.length).toBe(1)
    expect(rows.length).toBe(1)
    expect(rows[0]?.status).toBe("pending")
  })
})

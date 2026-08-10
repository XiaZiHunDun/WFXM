import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { appendEvents, loadStream, nextVersion, OptimisticConcurrencyError } from "./event-store.js"
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
})

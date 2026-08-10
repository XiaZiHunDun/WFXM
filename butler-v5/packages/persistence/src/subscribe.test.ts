import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { appendEvents, subscribeStream } from "./event-store.js"
import { makeTestDb } from "./testing.js"

describe("subscribe", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  beforeEach(async () => {
    db = await makeTestDb()
  })
  afterEach(async () => {
    await db.close()
  })

  it("invokes handler for each newly appended event in the same stream", async () => {
    const received: number[] = []
    const handler = (e: { streamVersion: number }) => received.push(e.streamVersion)
    const cancel = subscribeStream(db.db, "s-sub", handler)
    await appendEvents(
      db.db,
      "s-sub",
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
    await new Promise((r) => setTimeout(r, 30))
    cancel()
    expect(received).toEqual([1])
  })

  it("stop handler from previous subscription to apply to new event", async () => {
    const received: number[] = []
    const cancel = subscribeStream(db.db, "s-stop", (e) => received.push(e.streamVersion))
    cancel()
    await appendEvents(
      db.db,
      "s-stop",
      { _tag: "A" },
      {
        eventId: "e1",
        eventType: "A",
        eventVersion: 1,
        correlationId: "c1",
        occurredAt: new Date(),
        actor: { kind: "system", id: "test" },
      },
    )
    await new Promise((r) => setTimeout(r, 30))
    expect(received).toEqual([])
  })
})

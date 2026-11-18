import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { EventBridge, type EventBridgeConfig } from "./event-bridge.js"
import { appendEvents } from "./event-store.js"
import { makeTestDb } from "./testing.js"

describe("EventBridge", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let config: EventBridgeConfig
  beforeEach(async () => {
    db = await makeTestDb()
    config = { db, workerId: "test-worker", leaseMs: 5_000 }
  })
  afterEach(async () => {
    await db.close()
  })

  const actor = { kind: "user" as const, id: "owner-1" }

  it("appendConversationEvent persists an event readable via loadStream", async () => {
    const bridge = new EventBridge(config)
    await bridge.appendConversationEvent({
      streamId: "s-bridge-1",
      event: { _tag: "ConversationStarted", subject: "owner" },
      eventId: "e-1",
      eventType: "ConversationStarted",
      correlationId: "c-1",
      actor,
    })
    const rows = await bridge.loadStream("s-bridge-1")
    expect(rows).toHaveLength(1)
    expect(rows[0]?.eventType).toBe("ConversationStarted")
    expect(rows[0]?.streamVersion).toBe(1)
  })

  it("appendConversationEventWithOutbox enqueues an outbox message (worker delivers)", async () => {
    const bridge = new EventBridge(config)
    const payload = { body: "hello" }
    const outboxMessageId = await bridge.appendConversationEventWithOutbox({
      streamId: "s-bridge-2",
      event: { _tag: "UserMessageReceived" },
      eventId: "e-2",
      eventType: "UserMessageReceived",
      correlationId: "c-2",
      actor,
      outbox: { aggregateType: "conversation", payload },
    })
    expect(typeof outboxMessageId).toBe("string")

    const delivered: unknown[] = []
    const count = await bridge.runWorker(async (msg) => {
      delivered.push(msg.payload)
    })
    expect(count).toBe(1)
    expect(delivered).toEqual([payload])
    // delivered message is not re-claimed on a second run
    expect(await bridge.runWorker(async () => undefined)).toBe(0)
  })

  it("subscribe invokes handler for events appended after subscription", async () => {
    const bridge = new EventBridge(config)
    const received: string[] = []
    const cancel = bridge.subscribe("s-bridge-3", (e) => received.push(e.eventType))
    await appendEvents(
      db.db,
      "s-bridge-3",
      { _tag: "A" },
      {
        eventId: "e-3",
        eventType: "A",
        eventVersion: 1,
        correlationId: "c-3",
        occurredAt: new Date(),
        actor,
      },
    )
    await new Promise((r) => setTimeout(r, 30))
    cancel()
    expect(received).toEqual(["A"])
  })

  it("saveSnapshot/loadSnapshot round-trip payload and version", async () => {
    const bridge = new EventBridge(config)
    expect(await bridge.loadSnapshot("s-bridge-4")).toBeNull()
    await bridge.saveSnapshot("s-bridge-4", 3, { cursor: 7 })
    const snap = await bridge.loadSnapshot("s-bridge-4")
    expect(snap).toMatchObject({ streamVersion: 3, payload: { cursor: 7 } })
  })

  it("registerProjection + applyProjection / rebuildProjection track stream version", async () => {
    const bridge = new EventBridge(config)
    const seen: string[] = []
    bridge.registerProjection("count", async (e) => {
      seen.push(e.eventType)
    })
    for (const [i, type] of ["A", "B", "C"].entries()) {
      await appendEvents(
        db.db,
        "s-bridge-5",
        { _tag: type },
        {
          eventId: `e-5-${i}`,
          eventType: type,
          eventVersion: i + 1,
          correlationId: "c-5",
          occurredAt: new Date(),
          actor,
        },
      )
    }
    await bridge.applyProjection("s-bridge-5", "count")
    expect(seen).toEqual(["A", "B", "C"])

    // rebuild replays all events from scratch
    seen.length = 0
    await bridge.rebuildProjection("s-bridge-5", "count")
    expect(seen).toEqual(["A", "B", "C"])
  })
})

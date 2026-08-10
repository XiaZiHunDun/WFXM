import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { registerProjection, applyProjection, rebuildProjection } from "./projections.js"
import { projections } from "./schema.js"
import { appendEvents } from "./event-store.js"
import { makeTestDb } from "./testing.js"
import { eq } from "drizzle-orm"

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
    await applyProjection(db.db, "s-1", "counter")
    expect(count).toBe(1)
  })

  it("rebuildProjection replays all events for a stream", async () => {
    let count = 0
    registerProjection("counter", async () => {
      count++
    })
    await appendEvents(
      db.db,
      "s-2",
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
    await appendEvents(
      db.db,
      "s-2",
      { _tag: "B" },
      {
        eventId: "e2",
        eventType: "B",
        eventVersion: 2,
        correlationId: "c1",
        occurredAt: new Date(),
        actor: { kind: "system", id: "test" },
      },
    )
    await rebuildProjection(db.db, "s-2", "counter")
    expect(count).toBe(2)
  })

  it("projection state version is persisted between runs", async () => {
    let lastVersion = 0
    registerProjection("persist-test", async (e) => {
      lastVersion = e.streamVersion
    })
    await appendEvents(
      db.db,
      "s-3",
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
    await applyProjection(db.db, "s-3", "persist-test")
    expect(lastVersion).toBe(1)
    const rows = await db
      .select()
      .from(projections)
      .where(eq(projections.projectionName, "persist-test"))
    expect(rows[0]?.version).toBe(1)
  })
})

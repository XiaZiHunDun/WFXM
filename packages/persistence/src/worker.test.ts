import { describe, expect, it, beforeEach, afterEach, vi } from "vitest"
import { runWorkerOnce } from "./worker.js"
import { enqueueOutbox } from "./outbox.js"
import { outbox } from "./schema.js"
import { makeTestDb } from "./testing.js"

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

  it("calls failOutbox when handler throws", async () => {
    await enqueueOutbox(db.db, { streamId: "s-1", aggregateType: "X", payload: {} })
    const handler = vi.fn(async () => {
      throw new Error("downstream-down")
    })
    const processed = await runWorkerOnce(db.db, "w-1", 60_000, handler)
    expect(processed).toBe(0)
    const rows = await db.select().from(outbox)
    expect(rows[0]?.attemptCount).toBe(1)
    expect(rows[0]?.lastError).toContain("downstream-down")
    expect(rows[0]?.status).toBe("pending")
  })
})

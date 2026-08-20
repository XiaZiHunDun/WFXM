import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { eq, and } from "drizzle-orm"
import { enqueueOutbox, claimOutbox, completeOutbox, failOutbox } from "./outbox.js"
import { outbox } from "./schema.js"
import { makeTestDb } from "./testing.js"

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

  it("claimOutbox skips messages before nextAttemptAt", async () => {
    const id = await enqueueOutbox(db.db, {
      streamId: "s-backoff",
      aggregateType: "Conversation",
      payload: {},
    })
    await claimOutbox(db.db, "worker-1", 60_000)
    await failOutbox(db.db, id, "transient")
    const claimed = await claimOutbox(db.db, "worker-2", 60_000)
    expect(claimed.length).toBe(0)
    const rows = await db.select().from(outbox).where(eq(outbox.messageId, id))
    expect(rows[0]?.status).toBe("pending")
  })

  it("claimOutbox respects limit in SQL", async () => {
    for (let i = 0; i < 12; i++) {
      await enqueueOutbox(db.db, {
        streamId: "s-limit",
        aggregateType: "Conversation",
        payload: { i },
      })
    }
    const claimed = await claimOutbox(db.db, "worker-limit", 60_000, 10)
    expect(claimed.length).toBe(10)
    const pending = await db
      .select()
      .from(outbox)
      .where(and(eq(outbox.streamId, "s-limit"), eq(outbox.status, "pending")))
    expect(pending.length).toBe(2)
  })
})

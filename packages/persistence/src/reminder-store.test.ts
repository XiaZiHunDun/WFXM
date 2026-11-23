import { describe, expect, it } from "vitest"
import { createReminderStore, type ReminderRecord } from "./reminder-store.js"
import { makeTestDb } from "./testing.js"

function record(overrides: Partial<ReminderRecord> = {}): ReminderRecord {
  const now = 1_000_000
  return {
    id: crypto.randomUUID(),
    subject: "owner",
    wechatUserId: "u-owner",
    conversationId: "c1",
    content: "交周报",
    fireAtMs: now + 60_000,
    repeat: "once",
    status: "active",
    attemptCount: 0,
    lastAttemptAtMs: null,
    lastError: null,
    firedAtMs: null,
    createdAtMs: now,
    updatedAtMs: now,
    ...overrides,
  }
}

describe("reminderStore", () => {
  it("creates, lists and counts active reminders per subject", async () => {
    const db = await makeTestDb()
    try {
      const store = createReminderStore(db.db)
      await store.create(record({ content: "b", fireAtMs: 2_000 }))
      await store.create(record({ content: "a", fireAtMs: 1_500 }))
      await store.create(record({ subject: "other" }))

      const mine = await store.listActiveBySubject({ subject: "owner" })
      expect(mine.map((r) => r.content)).toEqual(["a", "b"])
      expect(await store.countActiveBySubject("owner")).toBe(2)
      const first = mine[0]
      expect(first && (await store.get(first.id))?.content).toBe("a")
    } finally {
      await db.close()
    }
  })

  it("returns only due reminders after the retry cooldown", async () => {
    const db = await makeTestDb()
    try {
      const store = createReminderStore(db.db)
      const due = record({ fireAtMs: 1_000 })
      const recentFailure = record({ fireAtMs: 1_000, lastAttemptAtMs: 9_500 })
      const future = record({ fireAtMs: 50_000 })
      await store.create(due)
      await store.create(recentFailure)
      await store.create(future)

      const rows = await store.listDue({ nowMs: 10_000, retryCooldownMs: 60_000 })
      expect(rows.map((r) => r.id)).toEqual([due.id])
    } finally {
      await db.close()
    }
  })

  it("marks once reminders done and advances recurring ones", async () => {
    const db = await makeTestDb()
    try {
      const store = createReminderStore(db.db)
      const once = record()
      const daily = record({ repeat: "daily" })
      await store.create(once)
      await store.create(daily)

      await store.markFired({ id: once.id, firedAtMs: 2_000 })
      await store.markFired({ id: daily.id, firedAtMs: 2_000, nextFireAtMs: 3_000 })

      expect(await store.get(once.id)).toMatchObject({ status: "done", firedAtMs: 2_000 })
      expect(await store.get(daily.id)).toMatchObject({
        status: "active",
        fireAtMs: 3_000,
        attemptCount: 0,
      })
    } finally {
      await db.close()
    }
  })

  it("records failed attempts and cancels only active own reminders", async () => {
    const db = await makeTestDb()
    try {
      const store = createReminderStore(db.db)
      const row = record()
      await store.create(row)

      await store.markAttemptFailed({ id: row.id, error: "network", attemptedAtMs: 5_000 })
      expect(await store.get(row.id)).toMatchObject({
        attemptCount: 1,
        lastAttemptAtMs: 5_000,
        lastError: "network",
      })

      expect(await store.cancel({ id: row.id, subject: "someone-else" })).toBe(false)
      expect(await store.cancel({ id: row.id, subject: "owner" })).toBe(true)
      expect(await store.cancel({ id: row.id, subject: "owner" })).toBe(false)
      expect((await store.get(row.id))?.status).toBe("cancelled")
    } finally {
      await db.close()
    }
  })
})

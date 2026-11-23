import { describe, expect, it } from "vitest"
import { createReminderStore, type ReminderRecord } from "@butler/persistence"
import { makeTestDb } from "@butler/persistence/testing.js"
import type { Wiring } from "./wiring.js"
import {
  formatReminderMessage,
  runReminderTick,
  startReminderWorkerIfEnabled,
} from "./reminder-worker.js"

function record(overrides: Partial<ReminderRecord> = {}): ReminderRecord {
  const now = 1_000_000
  return {
    id: crypto.randomUUID(),
    subject: "u-owner",
    wechatUserId: "u-owner",
    conversationId: "c1",
    content: "喝水",
    fireAtMs: now - 1_000,
    repeat: "once",
    status: "active",
    attemptCount: 0,
    lastAttemptAtMs: null,
    lastError: null,
    firedAtMs: null,
    createdAtMs: now - 10_000,
    updatedAtMs: now - 10_000,
    ...overrides,
  }
}

async function setup() {
  const db = await makeTestDb()
  const store = createReminderStore(db.db)
  const wiring = { reminderStore: store, channels: new Map() } as unknown as Wiring
  return { db, store, wiring }
}

describe("runReminderTick", () => {
  it("sends due reminders and marks once reminders done", async () => {
    const { db, store, wiring } = await setup()
    try {
      const reminder = record()
      await store.create(reminder)
      const sent: { to: string; text: string }[] = []
      const stats = await runReminderTick({
        wiring,
        env: {},
        nowMs: () => 1_000_000,
        send: async (args) => {
          sent.push({ to: args.to, text: args.text })
          return { ok: true }
        },
      })
      expect(stats).toEqual({ fired: 1, failed: 0 })
      expect(sent).toEqual([{ to: "u-owner", text: "【提醒】喝水" }])
      expect(await store.get(reminder.id)).toMatchObject({ status: "done", firedAtMs: 1_000_000 })
    } finally {
      await db.close()
    }
  })

  it("advances daily reminders to the next day", async () => {
    const { db, store, wiring } = await setup()
    try {
      const reminder = record({ repeat: "daily" })
      await store.create(reminder)
      await runReminderTick({
        wiring,
        env: {},
        nowMs: () => 1_000_000,
        send: async () => ({ ok: true }),
      })
      expect(await store.get(reminder.id)).toMatchObject({
        status: "active",
        fireAtMs: reminder.fireAtMs + 86_400_000,
      })
    } finally {
      await db.close()
    }
  })

  it("keeps active reminders on send failure and retries after the cooldown", async () => {
    const { db, store, wiring } = await setup()
    try {
      const reminder = record()
      await store.create(reminder)
      const stats = await runReminderTick({
        wiring,
        env: {},
        nowMs: () => 1_000_000,
        send: async () => ({ ok: false, reason: "network" }),
      })
      expect(stats).toEqual({ fired: 0, failed: 1 })
      expect(await store.get(reminder.id)).toMatchObject({
        status: "active",
        attemptCount: 1,
        lastError: "network",
      })

      const second = await runReminderTick({
        wiring,
        env: {},
        nowMs: () => 1_000_500,
        send: async () => ({ ok: true }),
      })
      expect(second).toEqual({ fired: 0, failed: 0 })
    } finally {
      await db.close()
    }
  })

  it("marks late deliveries in the message", () => {
    const reminder = record({ fireAtMs: 1_000_000 - 10 * 60_000 })
    const text = formatReminderMessage(reminder, 1_000_000)
    expect(text).toContain("【提醒】喝水")
    expect(text).toContain("补发")
  })

  it("does not start the worker when disabled", async () => {
    const { db, wiring } = await setup()
    try {
      expect(startReminderWorkerIfEnabled({ wiring, env: {} })).toBeNull()
    } finally {
      await db.close()
    }
  })
})

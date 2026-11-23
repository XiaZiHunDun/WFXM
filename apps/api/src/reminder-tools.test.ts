import { describe, expect, it } from "vitest"
import { createReminderStore, type ReminderRecord } from "@butler/persistence"
import { makeTestDb } from "@butler/persistence/testing.js"
import type { ButlerToolContext } from "./tools.js"
import { makeWeibutlerTools } from "./tools.js"
import {
  makeCancelReminderTool,
  makeCreateReminderTool,
  makeListRemindersTool,
} from "./reminder-tools.js"

function context(
  store: ReturnType<typeof createReminderStore>,
  env: NodeJS.ProcessEnv = {},
): ButlerToolContext {
  return {
    bridge: {} as ButlerToolContext["bridge"],
    conversationId: "c1",
    wechatUserId: "u-owner",
    env,
    reminderStore: store,
  }
}

async function run(
  tool: { run: (args: Record<string, unknown>) => Promise<unknown> },
  args: Record<string, unknown> = {},
) {
  return (await tool.run(args)) as {
    ok: boolean
    output?: string
    reason?: string
    meta?: Record<string, unknown>
  }
}

describe("reminder tools", () => {
  it("creates a reminder with owner-facing confirmation", async () => {
    const db = await makeTestDb()
    try {
      const store = createReminderStore(db.db)
      const tool = makeCreateReminderTool(context(store))
      const result = await run(tool, { content: "交周报", fireAt: "2999-01-01 09:30" })
      expect(result.ok).toBe(true)
      expect(result.output).toContain("已设置提醒")
      expect(result.output).toContain("2999-01-01 09:30")
      expect(result.output).toContain("交周报")

      const rows = await store.listActiveBySubject({ subject: "u-owner" })
      expect(rows).toHaveLength(1)
      expect(rows[0]).toMatchObject({ content: "交周报", repeat: "once", wechatUserId: "u-owner" })
    } finally {
      await db.close()
    }
  })

  it("rejects past once times and unknown repeat values", async () => {
    const db = await makeTestDb()
    try {
      const tool = makeCreateReminderTool(context(createReminderStore(db.db)))
      expect((await run(tool, { content: "x", fireAt: "2020-01-01 09:00" })).ok).toBe(false)
      const badRepeat = await run(tool, {
        content: "x",
        fireAt: "2999-01-01 09:00",
        repeat: "monthly",
      })
      expect(badRepeat.ok).toBe(false)
    } finally {
      await db.close()
    }
  })

  it("enforces the per-owner limit from env", async () => {
    const db = await makeTestDb()
    try {
      const store = createReminderStore(db.db)
      const tool = makeCreateReminderTool(
        context(store, { BUTLER_V5_REMINDERS_MAX_PER_OWNER: "1" }),
      )
      expect((await run(tool, { content: "a", fireAt: "2999-01-01 09:00" })).ok).toBe(true)
      const second = await run(tool, { content: "b", fireAt: "2999-01-02 09:00" })
      expect(second.ok).toBe(false)
      expect(second.reason).toContain("上限")
    } finally {
      await db.close()
    }
  })

  it("requires a WeChat recipient", async () => {
    const db = await makeTestDb()
    try {
      const store = createReminderStore(db.db)
      const ctx: ButlerToolContext = {
        bridge: {} as ButlerToolContext["bridge"],
        conversationId: "c1",
        env: {},
        reminderStore: store,
      }
      const result = await run(makeCreateReminderTool(ctx), {
        content: "a",
        fireAt: "2999-01-01 09:00",
      })
      expect(result.ok).toBe(false)
      expect(result.reason).toContain("微信")
    } finally {
      await db.close()
    }
  })

  it("lists only active reminders and reports an empty state", async () => {
    const db = await makeTestDb()
    try {
      const store = createReminderStore(db.db)
      const list = makeListRemindersTool(context(store))
      expect((await run(list)).output).toContain("没有提醒")
      await run(makeCreateReminderTool(context(store)), {
        content: "交周报",
        fireAt: "2999-01-01 09:00",
      })
      expect((await run(list)).output).toContain("交周报")
    } finally {
      await db.close()
    }
  })

  it("cancels by unique query and asks for a specific one when ambiguous", async () => {
    const db = await makeTestDb()
    try {
      const store = createReminderStore(db.db)
      const create = makeCreateReminderTool(context(store))
      const cancel = makeCancelReminderTool(context(store))
      await run(create, { content: "交周报", fireAt: "2999-01-01 09:00" })
      await run(create, { content: "交报销", fireAt: "2999-01-02 09:00" })

      const ambiguous = await run(cancel, { query: "交" })
      expect(ambiguous.ok).toBe(true)
      expect(ambiguous.output).toContain("多条")

      const unique = await run(cancel, { query: "周报" })
      expect(unique.ok).toBe(true)
      expect(unique.output).toContain("已取消")
      expect(await store.listActiveBySubject({ subject: "u-owner" })).toHaveLength(1)
    } finally {
      await db.close()
    }
  })

  it("registers reminder tools only when enabled", async () => {
    const db = await makeTestDb()
    try {
      const store = createReminderStore(db.db)
      const base = {
        ...context(store),
        mcpBundle: {
          runtimeTools: [],
          llmTools: [],
          mode: "off",
          discovered: [],
          servers: [],
          serverIdByCapability: {},
        },
      } as ButlerToolContext
      const off = makeWeibutlerTools({ ...base, env: {} }).map((t) => t.name as string)
      expect(off).not.toContain("create_reminder")
      const on = makeWeibutlerTools({
        ...base,
        env: { BUTLER_V5_REMINDERS_ENABLED: "1" },
      }).map((t) => t.name as string)
      expect(on).toEqual(
        expect.arrayContaining(["create_reminder", "list_reminders", "cancel_reminder"]),
      )
    } finally {
      await db.close()
    }
  })
})

describe("reminder record shape", () => {
  it("keeps owner and conversation on the stored row", async () => {
    const db = await makeTestDb()
    try {
      const store = createReminderStore(db.db)
      const record: ReminderRecord = {
        id: crypto.randomUUID(),
        subject: "u-owner",
        wechatUserId: "u-owner",
        conversationId: "wechat:c1",
        content: "喝水",
        fireAtMs: Date.now() + 60_000,
        repeat: "daily",
        status: "active",
        attemptCount: 0,
        lastAttemptAtMs: null,
        lastError: null,
        firedAtMs: null,
        createdAtMs: Date.now(),
        updatedAtMs: Date.now(),
      }
      await store.create(record)
      expect(await store.get(record.id)).toMatchObject({
        conversationId: "wechat:c1",
        repeat: "daily",
      })
    } finally {
      await db.close()
    }
  })
})

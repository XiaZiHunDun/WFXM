import { describe, expect, it } from "vitest"
import type { ButlerSessionRecord } from "@butler/ports/core/butler-session.js"
import { DrizzleButlerSessionStore } from "./butler-session-store.js"
import { makeTestDb } from "./testing.js"

function record(overrides: Partial<ButlerSessionRecord> = {}): ButlerSessionRecord {
  return {
    conversationId: "conv-1",
    userId: "user-1",
    projectId: "proj-1",
    messages: [
      { role: "user", content: "帮我看看登录超时" },
      { role: "assistant", content: "先看网关日志。" },
    ],
    createdAt: "2026-11-17T00:00:00.000Z",
    updatedAt: "2026-11-17T00:01:00.000Z",
    ...overrides,
  }
}

describe("DrizzleButlerSessionStore", () => {
  it("round-trips a session transcript", async () => {
    const db = await makeTestDb()
    try {
      const store = new DrizzleButlerSessionStore(db)
      await store.save(record())

      const loaded = await store.load("conv-1")
      expect(loaded).toEqual(record())
    } finally {
      await db.close()
    }
  })

  it("round-trips an optional summary and a missing project", async () => {
    const db = await makeTestDb()
    try {
      const store = new DrizzleButlerSessionStore(db)
      const input: ButlerSessionRecord = {
        conversationId: "conv-2",
        userId: "user-1",
        messages: [{ role: "user", content: "hi" }],
        summary: "用户打了招呼。",
        createdAt: "2026-11-17T00:00:00.000Z",
        updatedAt: "2026-11-17T00:00:00.000Z",
      }
      await store.save(input)

      const loaded = await store.load("conv-2")
      expect(loaded).toEqual(input)
      expect(loaded?.projectId).toBeUndefined()
    } finally {
      await db.close()
    }
  })

  it("updates an existing session without resetting createdAt", async () => {
    const db = await makeTestDb()
    try {
      const store = new DrizzleButlerSessionStore(db)
      await store.save(record())
      await store.save(
        record({
          messages: [
            { role: "user", content: "帮我看看登录超时" },
            { role: "assistant", content: "先看网关日志。" },
            { role: "user", content: "好" },
          ],
          summary: "已给出排查方向。",
          updatedAt: "2026-11-17T00:05:00.000Z",
        }),
      )

      const loaded = await store.load("conv-1")
      expect(loaded?.messages).toHaveLength(3)
      expect(loaded?.summary).toBe("已给出排查方向。")
      expect(loaded?.createdAt).toBe("2026-11-17T00:00:00.000Z")
      expect(loaded?.updatedAt).toBe("2026-11-17T00:05:00.000Z")
    } finally {
      await db.close()
    }
  })

  it("deletes a session and returns null for unknown ids", async () => {
    const db = await makeTestDb()
    try {
      const store = new DrizzleButlerSessionStore(db)
      await store.save(record())
      await store.delete("conv-1")

      expect(await store.load("conv-1")).toBeNull()
      expect(await store.load("missing")).toBeNull()
    } finally {
      await db.close()
    }
  })
})

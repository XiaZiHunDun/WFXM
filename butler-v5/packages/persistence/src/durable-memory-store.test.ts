import { describe, expect, it } from "vitest"
import { createDurableMemoryRecord } from "@butler/domain/knowledge/durable-memory.js"
import { createDurableMemoryStore } from "./durable-memory-store.js"
import { makeTestDb } from "./testing.js"

describe("durableMemoryStore", () => {
  it("persists, lists, confirms cascade-delete by messageId", async () => {
    const db = await makeTestDb()
    try {
      const store = createDurableMemoryStore(db.db)
      const created = createDurableMemoryRecord({
        subject: "owner",
        content: "偏好简洁",
        sourceKind: "message",
        provenance: { messageId: "msg-1", conversationId: "c-1" },
        nowMs: Date.parse("2026-08-21T00:00:00Z"),
      })
      expect(created.ok).toBe(true)
      if (!created.ok) return
      await store.create(created.value)
      const listed = await store.listBySubject({ subject: "owner" })
      expect(listed).toHaveLength(1)
      expect(listed[0]?.status).toBe("candidate")

      const removed = await store.deleteBySourceMessageId("msg-1")
      expect(removed).toBe(1)
      expect(await store.listBySubject({ subject: "owner" })).toHaveLength(0)
    } finally {
      await db.close()
    }
  })
})

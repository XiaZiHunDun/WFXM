import { describe, expect, it } from "vitest"
import {
  confirmDurableMemory,
  createDurableMemoryRecord,
  rejectDurableMemory,
  type DurableMemoryStatus,
} from "@butler/domain/knowledge/durable-memory.js"
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

  it("cascades durable memory when its source document is deleted", async () => {
    const db = await makeTestDb()
    try {
      const store = createDurableMemoryStore(db.db)
      const made = createDurableMemoryRecord({
        subject: "owner",
        content: "文档摘录",
        sourceKind: "document",
        provenance: { documentId: "doc-9" },
        nowMs: Date.parse("2026-08-21T00:00:00Z"),
      })
      expect(made.ok).toBe(true)
      if (!made.ok) return
      await store.create(made.value)
      expect(await store.deleteBySourceDocumentId("doc-9")).toBe(1)
      expect((await store.listBySubject({ subject: "owner" })).length).toBe(0)
    } finally {
      await db.close()
    }
  })

  it("persists confirm/reject and filters recall by confirmed status", async () => {
    const db = await makeTestDb()
    try {
      const store = createDurableMemoryStore(db.db)
      const cand = createDurableMemoryRecord({
        subject: "owner",
        content: "偏好",
        sourceKind: "message",
        provenance: { messageId: "m-1" },
        nowMs: Date.parse("2026-08-21T00:00:00Z"),
      })
      const rej = createDurableMemoryRecord({
        subject: "owner",
        content: "被拒",
        sourceKind: "message",
        provenance: { messageId: "m-2" },
        nowMs: Date.parse("2026-08-21T00:00:00Z") + 1,
      })
      expect(cand.ok && rej.ok).toBe(true)
      if (!cand.ok || !rej.ok) return
      await store.create(cand.value)
      await store.create(rej.value)

      await store.update(confirmDurableMemory(cand.value, Date.parse("2026-08-22T00:00:00Z")))
      await store.update(rejectDurableMemory(rej.value, Date.parse("2026-08-22T00:00:00Z")))

      const confirmed = await store.listBySubject({ subject: "owner", status: "confirmed" })
      expect(confirmed.map((r) => r.content)).toEqual(["偏好"])
      const rejected = await store.listBySubject({ subject: "owner", status: "rejected" })
      expect(rejected.map((r) => r.content)).toEqual(["被拒"])
    } finally {
      await db.close()
    }
  })

  it("listBySubject skips records by offset", async () => {
    const db = await makeTestDb()
    try {
      const store = createDurableMemoryStore(db.db)
      for (let i = 0; i < 6; i++) {
        const made = createDurableMemoryRecord({
          subject: "owner",
          content: `seed-${i}`,
          sourceKind: "owner",
          status: "candidate",
          nowMs: Date.parse("2026-09-01T00:00:00Z") + i * 1000,
        })
        if (!made.ok) throw new Error(made.reason)
        await store.create(made.value)
      }
      const page1 = await store.listBySubject({ subject: "owner", limit: 3, offset: 0 })
      const page2 = await store.listBySubject({ subject: "owner", limit: 3, offset: 3 })
      expect(page1).toHaveLength(3)
      expect(page2).toHaveLength(3)
      const page1Ids = new Set(page1.map((r) => r.id))
      expect(page2.every((r) => !page1Ids.has(r.id))).toBe(true)
      const noOffset = await store.listBySubject({ subject: "owner", limit: 3 })
      expect(noOffset.map((r) => r.id)).toEqual(page1.map((r) => r.id))
    } finally {
      await db.close()
    }
  })

  it("countBySubject returns total / per-status counts", async () => {
    const db = await makeTestDb()
    try {
      const store = createDurableMemoryStore(db.db)
      const all: { content: string; status: DurableMemoryStatus }[] = [
        { content: "a", status: "candidate" },
        { content: "b", status: "candidate" },
        { content: "c", status: "candidate" },
        { content: "d", status: "confirmed" },
        { content: "e", status: "confirmed" },
        { content: "f", status: "rejected" },
      ]
      for (const item of all) {
        const made = createDurableMemoryRecord({
          subject: "owner",
          content: item.content,
          sourceKind: "owner",
          status: item.status,
        })
        if (!made.ok) throw new Error(made.reason)
        await store.create(made.value)
      }
      expect(await store.countBySubject({ subject: "owner" })).toBe(6)
      expect(await store.countBySubject({ subject: "owner", status: "candidate" })).toBe(3)
      expect(await store.countBySubject({ subject: "owner", status: "confirmed" })).toBe(2)
      expect(await store.countBySubject({ subject: "owner", status: "rejected" })).toBe(1)
      expect(await store.countBySubject({ subject: "other" })).toBe(0)
    } finally {
      await db.close()
    }
  })
})

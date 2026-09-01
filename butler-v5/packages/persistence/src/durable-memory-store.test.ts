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

  it("listExpiredCandidates returns candidates older than threshold", async () => {
    const db = await makeTestDb()
    try {
      const store = createDurableMemoryStore(db.db)
      const baseMs = Date.parse("2026-09-01T00:00:00Z")
      for (let i = 0; i < 3; i++) {
        const made = createDurableMemoryRecord({
          subject: "owner",
          content: `seed-${i}`,
          sourceKind: "owner",
          status: "candidate",
          nowMs: baseMs + i * 1000,
        })
        if (!made.ok) throw new Error(made.reason)
        await store.create(made.value)
      }
      const older = await store.listExpiredCandidates({
        olderThanMs: baseMs + 2000,
        limit: 100,
      })
      expect(older).toHaveLength(2)
    } finally {
      await db.close()
    }
  })

  it("listExpiredCandidates excludes confirmed and rejected", async () => {
    const db = await makeTestDb()
    try {
      const store = createDurableMemoryStore(db.db)
      const baseMs = Date.parse("2026-09-01T00:00:00Z")
      const idsByStatus: Record<DurableMemoryStatus, string> = {
        candidate: "",
        confirmed: "",
        rejected: "",
        expired: "",
      }
      for (const status of ["candidate", "confirmed", "rejected"] as const) {
        const made = createDurableMemoryRecord({
          subject: "owner",
          content: `seed-${status}`,
          sourceKind: "owner",
          status,
          nowMs: baseMs,
        })
        if (!made.ok) throw new Error(made.reason)
        await store.create(made.value)
        idsByStatus[status] = made.value.id
      }
      const older = await store.listExpiredCandidates({
        olderThanMs: baseMs + 1000,
        limit: 100,
      })
      expect(older).toHaveLength(1)
      expect(older[0]?.id).toBe(idsByStatus.candidate)
    } finally {
      await db.close()
    }
  })

  it("listExpiredCandidates respects limit", async () => {
    const db = await makeTestDb()
    try {
      const store = createDurableMemoryStore(db.db)
      const baseMs = Date.parse("2026-09-01T00:00:00Z")
      for (let i = 0; i < 5; i++) {
        const made = createDurableMemoryRecord({
          subject: "owner",
          content: `seed-${i}`,
          sourceKind: "owner",
          status: "candidate",
          nowMs: baseMs + i * 1000,
        })
        if (!made.ok) throw new Error(made.reason)
        await store.create(made.value)
      }
      const older = await store.listExpiredCandidates({
        olderThanMs: baseMs + 10000,
        limit: 3,
      })
      expect(older).toHaveLength(3)
    } finally {
      await db.close()
    }
  })

  it("markExpired updates status to 'expired' for candidates", async () => {
    const db = await makeTestDb()
    try {
      const store = createDurableMemoryStore(db.db)
      const made = createDurableMemoryRecord({
        subject: "owner",
        content: "to-expire",
        sourceKind: "owner",
        status: "candidate",
      })
      if (!made.ok) throw new Error(made.reason)
      await store.create(made.value)
      const results = await store.markExpired([made.value.id])
      expect(results).toHaveLength(1)
      expect(results[0]?.updated).toBe(true)
      const after = await store.get(made.value.id)
      expect(after?.status).toBe("expired")
    } finally {
      await db.close()
    }
  })

  it("markExpired is idempotent — already expired returns updated=false", async () => {
    const db = await makeTestDb()
    try {
      const store = createDurableMemoryStore(db.db)
      const made = createDurableMemoryRecord({
        subject: "owner",
        content: "to-expire-twice",
        sourceKind: "owner",
        status: "candidate",
      })
      if (!made.ok) throw new Error(made.reason)
      await store.create(made.value)
      await store.markExpired([made.value.id])
      const second = await store.markExpired([made.value.id])
      expect(second[0]?.updated).toBe(false)
    } finally {
      await db.close()
    }
  })

  it("findCandidatesForDedup returns candidates matching subject + statuses within window", async () => {
    const db = await makeTestDb()
    try {
      const store = createDurableMemoryStore(db.db)
      const baseMs = Date.parse("2026-09-01T00:00:00Z")
      for (const status of ["candidate", "confirmed", "rejected"] as const) {
        const made = createDurableMemoryRecord({
          subject: "owner",
          content: `seed-${status}-unique`,
          sourceKind: "owner",
          status,
          nowMs: baseMs,
        })
        if (!made.ok) throw new Error(made.reason)
        await store.create(made.value)
      }
      const result = await store.findCandidatesForDedup({
        subject: "owner",
        statuses: ["candidate", "confirmed", "rejected"],
        recentMs: 90 * 24 * 3_600_000,
        limit: 50,
      })
      expect(result).toHaveLength(3)
      expect(result.map((r) => r.status).sort()).toEqual(["candidate", "confirmed", "rejected"])
    } finally {
      await db.close()
    }
  })

  it("findCandidatesForDedup respects limit", async () => {
    const db = await makeTestDb()
    try {
      const store = createDurableMemoryStore(db.db)
      const baseMs = Date.parse("2026-09-01T00:00:00Z")
      for (let i = 0; i < 5; i++) {
        const made = createDurableMemoryRecord({
          subject: "owner",
          content: `seed-${i}`,
          sourceKind: "owner",
          status: "candidate",
          nowMs: baseMs + i * 1000,
        })
        if (!made.ok) throw new Error(made.reason)
        await store.create(made.value)
      }
      const result = await store.findCandidatesForDedup({
        subject: "owner",
        statuses: ["candidate"],
        recentMs: 90 * 24 * 3_600_000,
        limit: 3,
      })
      expect(result).toHaveLength(3)
    } finally {
      await db.close()
    }
  })

  it("markExpired does not affect confirmed or rejected", async () => {
    const db = await makeTestDb()
    try {
      const store = createDurableMemoryStore(db.db)
      const confirmed = createDurableMemoryRecord({
        subject: "owner",
        content: "c",
        sourceKind: "owner",
        status: "confirmed",
      })
      const rejected = createDurableMemoryRecord({
        subject: "owner",
        content: "r",
        sourceKind: "owner",
        status: "rejected",
      })
      if (!confirmed.ok || !rejected.ok) throw new Error("seed failed")
      await store.create(confirmed.value)
      await store.create(rejected.value)
      const results = await store.markExpired([confirmed.value.id, rejected.value.id])
      expect(results.every((r) => !r.updated)).toBe(true)
      const cAfter = await store.get(confirmed.value.id)
      const rAfter = await store.get(rejected.value.id)
      expect(cAfter?.status).toBe("confirmed")
      expect(rAfter?.status).toBe("rejected")
    } finally {
      await db.close()
    }
  })
})

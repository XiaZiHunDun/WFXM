import { describe, expect, it } from "vitest"
import { ingestDocumentRecord } from "@butler/domain/knowledge/document-ingest.js"
import { createDocumentStore } from "./document-store.js"
import { createDurableMemoryStore } from "./durable-memory-store.js"
import { createDurableMemoryRecord } from "@butler/domain/knowledge/durable-memory.js"
import { makeTestDb } from "./testing.js"

describe("documentStore", () => {
  it("persists documents and cascades memory delete by documentId", async () => {
    const db = await makeTestDb()
    try {
      const docs = createDocumentStore(db.db)
      const memories = createDurableMemoryStore(db.db)
      const created = ingestDocumentRecord({
        subject: "owner",
        title: "runbook",
        format: "markdown",
        text: "# Deploy\nstep 1",
        nowMs: Date.parse("2026-08-21T00:00:00Z"),
      })
      expect(created.ok).toBe(true)
      if (!created.ok) return
      await docs.create(created.value)

      const listed = await docs.listBySubject({ subject: "owner" })
      expect(listed).toHaveLength(1)

      const mem = createDurableMemoryRecord({
        subject: "owner",
        content: "部署看 runbook",
        sourceKind: "document",
        provenance: { documentId: created.value.id },
        nowMs: Date.now(),
      })
      expect(mem.ok).toBe(true)
      if (!mem.ok) return
      await memories.create(mem.value)

      await docs.delete(created.value.id)
      const cascaded = await memories.deleteBySourceDocumentId(created.value.id)
      expect(cascaded).toBe(1)
    } finally {
      await db.close()
    }
  })

  it("get round-trips, delete-missing returns false, list newest-first + limit", async () => {
    const db = await makeTestDb()
    try {
      const docs = createDocumentStore(db.db)
      const mk = (id: string, title: string, now: number) => {
        const made = ingestDocumentRecord({
          id,
          subject: "owner",
          title,
          format: "markdown",
          text: `body ${title}`,
          nowMs: now,
        })
        expect(made.ok).toBe(true)
        if (!made.ok) return null
        return made.value
      }
      const a = mk("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "first", Date.parse("2026-08-21T00:00:00Z"))
      const b = mk("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "later", Date.parse("2026-08-22T00:00:00Z"))
      expect(a && b).toBeTruthy()
      if (!a || !b) return
      await docs.create(a)
      await docs.create(b)

      const got = await docs.get(a.id)
      expect(got?.title).toBe("first")
      expect(await docs.get("ffffffff-ffff-ffff-ffff-ffffffffffff")).toBeNull()

      expect(await docs.delete("ffffffff-ffff-ffff-ffff-ffffffffffff")).toBe(false)
      expect(await docs.delete(a.id)).toBe(true)

      const listed = await docs.listBySubject({ subject: "owner", limit: 1 })
      expect(listed.map((r) => r.id)).toEqual([b.id])
    } finally {
      await db.close()
    }
  })
})

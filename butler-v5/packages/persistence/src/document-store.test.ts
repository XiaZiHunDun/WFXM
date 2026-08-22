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
})

import { describe, expect, it } from "vitest"
import { createProjectKnowledgeRecord } from "@butler/domain/knowledge/project-knowledge.js"
import { makeTestDb } from "./testing.js"
import { createProjectKnowledgeStore } from "./project-knowledge-store.js"

describe("projectKnowledgeStore", () => {
  it("creates, lists, and deletes by project", async () => {
    const db = await makeTestDb()
    try {
      const store = createProjectKnowledgeStore(db.db)
      const created = createProjectKnowledgeRecord({
        projectId: "WFXM",
        title: "note",
        kind: "manual_note",
        body: "hello project knowledge",
        nowMs: 1000,
      })
      if (!created.ok) throw new Error(created.reason)
      await store.create(created.value)
      const listed = await store.listByProject({ projectId: "WFXM" })
      expect(listed).toHaveLength(1)
      expect(listed[0]?.title).toBe("note")
      const ok = await store.delete(created.value.id)
      expect(ok).toBe(true)
    } finally {
      await db.close()
    }
  })
})

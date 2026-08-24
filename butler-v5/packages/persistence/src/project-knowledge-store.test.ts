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

      const found = await store.findBySourcePath({
        projectId: "WFXM",
        sourcePath: "docs/note.md",
      })
      expect(found).toBeNull()
      const snap = createProjectKnowledgeRecord({
        projectId: "WFXM",
        title: "snap",
        kind: "file_snapshot",
        body: "v1",
        provenance: { sourcePath: "docs/note.md", sourceMtimeMs: 1, sourceSize: 2 },
        nowMs: 2000,
      })
      if (!snap.ok) throw new Error(snap.reason)
      await store.create(snap.value)
      const hit = await store.findBySourcePath({
        projectId: "WFXM",
        sourcePath: "docs/note.md",
      })
      expect(hit?.id).toBe(snap.value.id)
      const updated = createProjectKnowledgeRecord({
        id: snap.value.id,
        projectId: "WFXM",
        title: "snap2",
        kind: "file_snapshot",
        body: "v2",
        provenance: { sourcePath: "docs/note.md", sourceMtimeMs: 3, sourceSize: 4 },
        nowMs: 3000,
      })
      if (!updated.ok) throw new Error(updated.reason)
      await store.update({ ...updated.value, createdAt: snap.value.createdAt })
      const hit2 = await store.get(snap.value.id)
      expect(hit2?.title).toBe("snap2")
    } finally {
      await db.close()
    }
  })
})

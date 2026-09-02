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

  it("listAllProjects returns distinct non-empty project ids", async () => {
    const db = await makeTestDb()
    try {
      const store = createProjectKnowledgeStore(db.db)
      const noProjects = await store.listAllProjects()
      expect(noProjects).toEqual([])

      const a = createProjectKnowledgeRecord({ projectId: "WFXM", title: "a", kind: "manual_note", body: "x" })
      if (!a.ok) throw new Error(a.reason)
      await store.create(a.value)
      const b = createProjectKnowledgeRecord({ projectId: "WFXM", title: "b", kind: "manual_note", body: "y" })
      if (!b.ok) throw new Error(b.reason)
      await store.create(b.value)
      const c = createProjectKnowledgeRecord({ projectId: "LingWen", title: "c", kind: "manual_note", body: "z" })
      if (!c.ok) throw new Error(c.reason)
      await store.create(c.value)

      const projects = await store.listAllProjects()
      expect(projects).toEqual(["LingWen", "WFXM"])
    } finally {
      await db.close()
    }
  })

  it("listByProjects recalls across projects with dedup and per-project limit", async () => {
    const db = await makeTestDb()
    try {
      const store = createProjectKnowledgeStore(db.db)
      for (const p of ["WFXM", "WFXM", "LingWen"]) {
        const r = createProjectKnowledgeRecord({ projectId: p, title: "t", kind: "manual_note", body: "body" })
        if (!r.ok) throw new Error(r.reason)
        await store.create(r.value)
      }
      const all = await store.listByProjects({ projectIds: ["WFXM", "LingWen"] })
      expect(all.map((r) => r.projectId).sort()).toEqual(["LingWen", "WFXM", "WFXM"])
      const limited = await store.listByProjects({ projectIds: ["WFXM", "LingWen"], perProjectLimit: 1 })
      expect(limited).toHaveLength(2)
    } finally {
      await db.close()
    }
  })
})

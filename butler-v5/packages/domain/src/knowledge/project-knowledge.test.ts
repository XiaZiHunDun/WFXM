import { describe, expect, it } from "vitest"
import {
  createProjectKnowledgeRecord,
  projectKnowledgeFromDocument,
  selectProjectKnowledgeForRecall,
  selectProjectKnowledgeForWorkingSet,
} from "./project-knowledge.js"
import type { DocumentRecord } from "./document-ingest.js"

describe("project knowledge", () => {
  it("creates a manual note record", () => {
    const created = createProjectKnowledgeRecord({
      projectId: "WFXM",
      title: "MCP decision",
      kind: "manual_note",
      body: "Use manifest for multi-server MCP",
      nowMs: 1000,
    })
    expect(created.ok).toBe(true)
    if (created.ok) {
      expect(created.value.projectId).toBe("WFXM")
      expect(created.value.kind).toBe("manual_note")
    }
  })

  it("promotes a ready document into project knowledge", () => {
    const doc: DocumentRecord = {
      id: "doc-1",
      subject: "owner",
      title: "Design",
      format: "markdown",
      mimeType: "text/markdown",
      byteSize: 10,
      extractedText: "MCP uses manifest",
      status: "ready",
      failureReason: null,
      provenance: { sourcePath: "butler-v5/DESIGN.md" },
      createdAt: 1,
      updatedAt: 1,
    }
    const created = projectKnowledgeFromDocument({ projectId: "wechat", document: doc })
    expect(created.ok).toBe(true)
    if (created.ok) {
      expect(created.value.kind).toBe("ingested_document")
      expect(created.value.provenance.documentId).toBe("doc-1")
    }
  })

  it("selects by substring query", () => {
    const a = createProjectKnowledgeRecord({
      projectId: "WFXM",
      title: "A",
      kind: "manual_note",
      body: "alpha beta",
      nowMs: 1,
    })
    const b = createProjectKnowledgeRecord({
      projectId: "WFXM",
      title: "B",
      kind: "manual_note",
      body: "gamma",
      nowMs: 2,
    })
    if (!a.ok || !b.ok) throw new Error("setup failed")
    const selected = selectProjectKnowledgeForRecall({
      records: [a.value, b.value],
      query: "alpha",
      limit: 5,
    })
    expect(selected).toHaveLength(1)
    expect(selected[0]?.title).toBe("A")
  })

  it("working set falls back to recent items when query does not match", () => {
    const a = createProjectKnowledgeRecord({
      projectId: "WFXM",
      title: "older",
      kind: "manual_note",
      body: "alpha",
      nowMs: 1,
    })
    const b = createProjectKnowledgeRecord({
      projectId: "WFXM",
      title: "newer",
      kind: "manual_note",
      body: "beta",
      nowMs: 2,
    })
    if (!a.ok || !b.ok) throw new Error("setup failed")
    const selected = selectProjectKnowledgeForWorkingSet({
      records: [a.value, b.value],
      query: "this long user message matches nothing in ingest",
      limit: 2,
    })
    expect(selected).toHaveLength(2)
    expect(selected[0]?.title).toBe("newer")
  })
})

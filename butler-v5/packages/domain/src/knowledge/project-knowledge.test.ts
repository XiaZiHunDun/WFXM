import { describe, expect, it } from "vitest"
import {
  createProjectKnowledgeRecord,
  expandRecallProjectIds,
  formatCrossProjectRecall,
  projectKnowledgeFromDocument,
  resolveProjectKnowledgeInboundProjectId,
  selectProjectKnowledgeForRecall,
  selectProjectKnowledgeForWorkingSet,
} from "./project-knowledge.js"
import { formatProjectKnowledgePrefix, formatProjectKnowledgeSnippet, matchProjectKnowledgeQuery, normalizeProjectId } from "./project-knowledge.js"
import type { DocumentRecord } from "./document-ingest.js"

describe("project knowledge", () => {
  it("maps inbound wechat projectId to WFXM for PK by default", () => {
    expect(resolveProjectKnowledgeInboundProjectId("wechat")).toBe("WFXM")
    expect(resolveProjectKnowledgeInboundProjectId("WFXM")).toBe("WFXM")
    expect(resolveProjectKnowledgeInboundProjectId("LingWen")).toBe("LingWen")
  })

  it("honours BUTLER_V5_PROJECT_KNOWLEDGE_INBOUND_MAP override", () => {
    const env = {
      BUTLER_V5_PROJECT_KNOWLEDGE_INBOUND_MAP: "wechat:WFXM,LingWen1:LingWen,灵文1号:LingWen",
    }
    expect(resolveProjectKnowledgeInboundProjectId("wechat", env)).toBe("WFXM")
    expect(resolveProjectKnowledgeInboundProjectId("LingWen1", env)).toBe("LingWen")
    expect(resolveProjectKnowledgeInboundProjectId("灵文1号", env)).toBe("LingWen")
  })

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

  it("expandRecallProjectIds defaults to the current project (backward compat)", () => {
    const r = expandRecallProjectIds({ contextProjectId: "WFXM" })
    expect(r).toEqual({ ok: true, projectIds: ["WFXM"] })
  })

  it("expandRecallProjectIds accepts an explicit cross-project projectId", () => {
    const r = expandRecallProjectIds({
      contextProjectId: "WFXM",
      requestedProjectId: "LingWen",
    })
    expect(r).toEqual({ ok: true, projectIds: ["LingWen"] })
  })

  it("expandRecallProjectIds expands a comma-separated projects list with dedup", () => {
    const r = expandRecallProjectIds({
      contextProjectId: "WFXM",
      projects: " WFXM, LingWen , WFXM, ",
    })
    expect(r).toEqual({ ok: true, projectIds: ["WFXM", "LingWen"] })
  })

  it("expandRecallProjectIds resolves * to all known projects", () => {
    const r = expandRecallProjectIds({
      contextProjectId: "WFXM",
      projects: "*",
      allProjectIds: ["LingWen", "WFXM"],
    })
    expect(r).toEqual({ ok: true, projectIds: ["LingWen", "WFXM"] })
  })

  it("expandRecallProjectIds prioritizes projects over projectId on conflict", () => {
    const r = expandRecallProjectIds({
      contextProjectId: "WFXM",
      requestedProjectId: "WFXM",
      projects: "LingWen",
    })
    expect(r).toEqual({ ok: true, projectIds: ["LingWen"] })
  })

  it("expandRecallProjectIds errors when neither project nor context is present", () => {
    const r = expandRecallProjectIds({ contextProjectId: "" })
    expect(r).toEqual({ ok: false, reason: "projectId is required for project knowledge recall" })
  })

  it("expandRecallProjectIds errors when * has no known projects", () => {
    const r = expandRecallProjectIds({ contextProjectId: "WFXM", projects: "*" })
    expect(r).toEqual({ ok: false, reason: "no projects known" })
  })

  it("formatCrossProjectRecall keeps single-project output without a prefix", () => {
    const a = createProjectKnowledgeRecord({
      projectId: "WFXM",
      title: "Note",
      kind: "manual_note",
      body: "alpha",
      nowMs: 1,
    })
    if (!a.ok) throw new Error(a.reason)
    const out = formatCrossProjectRecall({
      query: "",
      limit: 5,
      byProject: [{ projectId: "WFXM", records: [a.value] }],
    })
    expect(out).toContain("[manual_note] Note")
    expect(out).not.toContain("[WFXM]")
  })

  it("formatCrossProjectRecall tags multiple projects and honours query + limit", () => {
    const a = createProjectKnowledgeRecord({ projectId: "WFXM", title: "A", kind: "manual_note", body: "alpha", nowMs: 1 })
    const b = createProjectKnowledgeRecord({ projectId: "LingWen", title: "B", kind: "manual_note", body: "rules", nowMs: 2 })
    const c = createProjectKnowledgeRecord({ projectId: "LingWen", title: "C", kind: "manual_note", body: "other", nowMs: 3 })
    if (!a.ok || !b.ok || !c.ok) throw new Error("setup failed")
    const out = formatCrossProjectRecall({
      query: "",
      limit: 2,
      byProject: [
        { projectId: "WFXM", records: [a.value] },
        { projectId: "LingWen", records: [b.value, c.value] },
      ],
    })
    expect(out).not.toBeNull()
    expect(out).toContain("[WFXM]")
    expect(out).toContain("[LingWen]")
    const matches = (out ?? "").match(/\d+\./g)
    expect(matches).toHaveLength(2)
  })

  it("formatCrossProjectRecall returns null on no match", () => {
    const a = createProjectKnowledgeRecord({ projectId: "WFXM", title: "A", kind: "manual_note", body: "alpha", nowMs: 1 })
    if (!a.ok) throw new Error(a.reason)
    expect(
      formatCrossProjectRecall({
        query: "no-match-xyz",
        limit: 5,
        byProject: [{ projectId: "WFXM", records: [a.value] }],
      }),
    ).toBeNull()
  })
})

type PkFixture = {
  readonly kind: string
  readonly title: string
  readonly body: string
  readonly provenance: { readonly note?: string; readonly sourcePath?: string }
}
function rec(overrides: Partial<PkFixture> = {}): PkFixture {
  return { kind: "decision", title: "Title", body: "body", provenance: {}, ...overrides }
}

describe("project knowledge pure helpers", () => {
  it("normalizes project id by trimming", () => {
    expect(normalizeProjectId("  proj-a  ")).toBe("proj-a")
    expect(normalizeProjectId("proj-a")).toBe("proj-a")
  })

  it("matches knowledge by substring query across title/body/note/path", () => {
    const r = rec({ title: "Deploy Notes", body: "uses kubectl", provenance: { note: "from ops", sourcePath: "ops/runbook.md" } })
    expect(matchProjectKnowledgeQuery(r, "kubectl")).toBe(true)
    expect(matchProjectKnowledgeQuery(r, "runbook")).toBe(true)
    expect(matchProjectKnowledgeQuery(r, "DEPLOY")).toBe(true)
    expect(matchProjectKnowledgeQuery(r, "unrelated")).toBe(false)
    expect(matchProjectKnowledgeQuery(r, "")).toBe(true)
  })

  it("formats a snippet with body truncation and optional path", () => {
    expect(formatProjectKnowledgeSnippet(rec({ title: "T", body: "abc" }), 5)).toBe("[decision] T\nabc")
    expect(formatProjectKnowledgeSnippet(rec({ title: "T", body: "abcdefgh" }), 4)).toBe("[decision] T\nabcd…")
    expect(formatProjectKnowledgeSnippet(rec({ kind: "fact", title: "T", body: "b", provenance: { sourcePath: "x.md" } }))).toBe("[fact] T path=x.md\nb")
  })

  it("formats the recall prefix as null for empty and numbered list otherwise", () => {
    expect(formatProjectKnowledgePrefix([])).toBeNull()
    expect(formatProjectKnowledgePrefix([rec({ title: "A", body: "a" }), rec({ title: "B", body: "b" })])).toContain("1. [")
    expect(formatProjectKnowledgePrefix([rec({ kind: "fact", title: "A", body: "a" })])).toBe(
      "Project Knowledge (confirmed ingest, substring recall):\n1. [fact] A\na",
    )
  })
})

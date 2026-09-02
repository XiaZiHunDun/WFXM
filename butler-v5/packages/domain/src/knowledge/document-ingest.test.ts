import { describe, expect, it } from "vitest"
import {
  formatDocumentSnippet,
  ingestDocumentRecord,
  parseDocumentFormat,
  selectDocumentsForRecall,
} from "./document-ingest.js"
import { defaultMimeForFormat, matchDocumentQuery } from "./document-ingest.js"

describe("document ingest", () => {
  it("parses named formats", () => {
    expect(parseDocumentFormat("txt")).toBe("plaintext")
    expect(parseDocumentFormat("markdown")).toBe("markdown")
    expect(parseDocumentFormat("pdf")).toBe("pdf")
    expect(parseDocumentFormat("docx")).toBeNull()
  })

  it("ingests plaintext and truncates long extract", () => {
    const created = ingestDocumentRecord({
      subject: "owner",
      title: "notes",
      format: "plaintext",
      text: "hello world",
      nowMs: 10,
    })
    expect(created.ok).toBe(true)
    if (!created.ok) return
    expect(created.value.status).toBe("ready")
    expect(created.value.mimeType).toBe("text/plain")

    const long = ingestDocumentRecord({
      subject: "owner",
      title: "big",
      format: "markdown",
      text: "x".repeat(50),
      maxExtractedChars: 20,
      nowMs: 11,
    })
    expect(long.ok).toBe(true)
    if (!long.ok) return
    expect(long.value.extractedText).toContain("[truncated]")
  })

  it("requires pre-extracted text for pdf", () => {
    expect(
      ingestDocumentRecord({
        subject: "owner",
        title: "scan",
        format: "pdf",
        text: "   ",
        nowMs: 1,
      }).ok,
    ).toBe(false)
  })

  it("selects by query and formats snippet", () => {
    const a = ingestDocumentRecord({
      id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      subject: "owner",
      title: "手册",
      format: "markdown",
      text: "部署步骤如下",
      nowMs: 1,
    })
    expect(a.ok).toBe(true)
    if (!a.ok) return
    const selected = selectDocumentsForRecall({
      records: [a.value],
      query: "部署",
      limit: 3,
    })
    expect(selected).toHaveLength(1)
    const first = selected[0]
    expect(first).toBeDefined()
    if (!first) return
    expect(formatDocumentSnippet(first)).toContain("手册")
  })

  it("rejects text exceeding maxInputChars and keeps provenance", () => {
    const tooBig = ingestDocumentRecord({
      subject: "owner",
      title: "huge",
      format: "markdown",
      text: "z".repeat(51),
      maxInputChars: 50,
      nowMs: 1,
    })
    expect(tooBig.ok).toBe(false)
    if (!tooBig.ok) expect(tooBig.reason).toContain("maxInputChars")

    const kept = ingestDocumentRecord({
      subject: "owner",
      title: "p",
      format: "plaintext",
      text: "body",
      provenance: { sourceFile: "docs/a.md", note: "imported 2026" },
      nowMs: 2,
    })
    expect(kept.ok).toBe(true)
    if (!kept.ok) return
    expect(kept.value.provenance).toEqual({ sourceFile: "docs/a.md", note: "imported 2026" })
  })

  it("select only ready documents and truncates snippet", () => {
    const a = ingestDocumentRecord({
      id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
      subject: "owner",
      title: "长文",
      format: "markdown",
      text: String("x").repeat(1200),
      nowMs: 1,
    })
    expect(a.ok).toBe(true)
    if (!a.ok) return
    const failed = { ...a.value, status: "failed", failureReason: "boom" }
    const selected = selectDocumentsForRecall({ records: [a.value, failed], query: "", limit: 5 })
    expect(selected).toHaveLength(1)
    expect(selected[0]?.status).toBe("ready")
    const snippet = formatDocumentSnippet(a.value, 30)
    expect(snippet.length).toBeLessThan(a.value.extractedText.length)
    expect(snippet.endsWith("...")).toBe(true)
  })
})

type DocFixture = {
  readonly title: string
  readonly extractedText: string
  readonly provenance: { readonly note?: string }
}
function doc(overrides: Partial<DocFixture> = {}): DocFixture {
  return { title: "Title", extractedText: "text", provenance: {}, ...overrides }
}

describe("document ingest pure helpers", () => {
  it("maps document format to default mime type", () => {
    expect(defaultMimeForFormat("markdown")).toBe("text/markdown")
    expect(defaultMimeForFormat("pdf")).toBe("application/pdf")
    expect(defaultMimeForFormat("html")).toBe("text/plain")
  })

  it("matches document by substring query across title/text/note", () => {
    const d = doc({ title: "README", extractedText: "install via npm", provenance: { note: "guide" } })
    expect(matchDocumentQuery(d, "npm")).toBe(true)
    expect(matchDocumentQuery(d, "guide")).toBe(true)
    expect(matchDocumentQuery(d, "missing")).toBe(false)
    expect(matchDocumentQuery(d, "")).toBe(true)
  })
})

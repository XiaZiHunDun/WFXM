import { describe, expect, it } from "vitest"
import {
  formatDocumentSnippet,
  ingestDocumentRecord,
  parseDocumentFormat,
  selectDocumentsForRecall,
} from "./document-ingest.js"

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
})

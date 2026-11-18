import { describe, expect, it } from "vitest"
import {
  chunkDocumentText,
  cosineSimilarity,
  formatChunkSnippet,
  formatDocumentSnippet,
  ingestDocumentRecord,
  parseDocumentFormat,
  scoreRecallText,
  selectDocumentChunksForRecall,
  selectDocumentsForRecall,
  tokenizeRecallQuery,
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
    const d = doc({
      title: "README",
      extractedText: "install via npm",
      provenance: { note: "guide" },
    })
    expect(matchDocumentQuery(d, "npm")).toBe(true)
    expect(matchDocumentQuery(d, "guide")).toBe(true)
    expect(matchDocumentQuery(d, "missing")).toBe(false)
    expect(matchDocumentQuery(d, "")).toBe(true)
  })
})

describe("chunk-level recall", () => {
  function ingested(text: string, title = "架构手册") {
    const created = ingestDocumentRecord({
      id: "doc-1",
      subject: "owner",
      title,
      format: "markdown",
      text,
      nowMs: 1,
    })
    if (!created.ok) throw new Error(created.reason)
    return created.value
  }

  it("chunks long text with stable citation ids", () => {
    const record = ingested(
      Array.from({ length: 20 }, (_, i) => `第 ${i} 段：内容 ${i}`).join("\n"),
    )
    const chunks = chunkDocumentText(record.extractedText, { maxChars: 120, overlap: 20 })
    expect(chunks.length).toBeGreaterThan(1)
    expect(chunks[0]?.index).toBe(0)
    expect(chunks[1]?.index).toBe(1)
    expect(chunks[0]?.start).toBe(0)
    expect(chunks[1]?.start ?? 0).toBeGreaterThan(0)
  })

  it("scores lexical overlap and tokenizes CJK bigrams", () => {
    expect(tokenizeRecallQuery("部署 流程")).toContain("部署")
    expect(tokenizeRecallQuery("部署流程")).toContain("部署")
    const hit = scoreRecallText("部署流程", "本文说明部署流程与回滚")
    expect(hit.score).toBe(1)
    expect(scoreRecallText("missing", "本文说明部署流程").score).toBe(0)
  })

  it("selects top chunks with citation and scoreKind", () => {
    const record = ingested(
      ["安装步骤：pnpm install", "部署流程：先灰度再全量", "回滚方案：保留上一版本"].join("\n"),
    )
    const hits = selectDocumentChunksForRecall({
      records: [record],
      query: "部署流程",
      limit: 3,
      chunkChars: 40,
    })
    expect(hits.length).toBeGreaterThan(0)
    expect(hits[0]?.score).toBeGreaterThan(0)
    expect(hits[0]?.chunk.docId).toBe("doc-1")
    expect(hits[0]?.chunk.chunkId.startsWith("doc-1#")).toBe(true)
    expect(hits[0]?.scoreKind).toBe("lexical")
    const first = hits[0]
    expect(first).toBeTruthy()
    const snippet = first ? formatChunkSnippet(first) : ""
    expect(snippet).toContain("doc:doc-1#")
    expect(snippet).toContain("score=")
  })

  it("hybrid recall matches paraphrases that lexical filtering drops", () => {
    const record = ingested("费用审批与发票提交步骤：先由直属主管审批，再提交发票。", "报销说明")
    const paraphrased = "怎么报销差旅费？"

    // 旧路径会先按子串过滤文档，改写提问直接 0 命中。
    expect(selectDocumentChunksForRecall({ records: [record], query: paraphrased, limit: 3 })).toHaveLength(0)

    const hybrid = selectDocumentChunksForRecall({
      records: [record],
      query: paraphrased,
      limit: 3,
      embedding: {
        queryEmbedding: [1, 0],
        chunkEmbedding: () => [0.98, 0.02],
      },
    })
    expect(hybrid.length).toBeGreaterThan(0)
    expect(hybrid[0]?.scoreKind).toBe("hybrid")
    expect(hybrid[0]?.semanticScore).toBeGreaterThan(0.9)
    expect(hybrid[0]?.score).toBeGreaterThan(0.4)
  })

  it("cosineSimilarity handles zero and mismatched vectors", () => {
    expect(cosineSimilarity([1, 0], [1, 0])).toBe(1)
    expect(cosineSimilarity([1, 0], [0, 1])).toBe(0)
    expect(cosineSimilarity([], [])).toBe(0)
    expect(cosineSimilarity([1], [1, 0])).toBe(0)
    expect(cosineSimilarity([0, 0], [1, 0])).toBe(0)
  })
})

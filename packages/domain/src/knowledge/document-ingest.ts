/**
 * Document ingest — named format providers (DESIGN §9 / P4).
 * Not RAG Studio; not default full-disk indexing; not Project Knowledge.
 */

export type DocumentId = string

/** Named ingest formats. Binary PDF/OCR parsers are out of MVP scope. */
export type DocumentFormat = "plaintext" | "markdown" | "pdf"

export type DocumentStatus = "ready" | "failed"

export interface DocumentProvenance {
  readonly conversationId?: string
  readonly messageId?: string
  /** Original path or URL label for residency audit (not auto-fetched). */
  readonly sourcePath?: string
  readonly note?: string
}

export interface DocumentRecord {
  readonly id: DocumentId
  readonly subject: string
  readonly title: string
  readonly format: DocumentFormat
  readonly mimeType: string
  readonly byteSize: number
  /** Extracted / provided text; truncated at ingest. */
  readonly extractedText: string
  readonly status: DocumentStatus
  readonly failureReason: string | null
  readonly provenance: DocumentProvenance
  readonly createdAt: number
  readonly updatedAt: number
}

export interface IngestDocumentInput {
  readonly id?: string
  readonly subject: string
  readonly title: string
  readonly format: DocumentFormat
  /** UTF-8 text body (required for all MVP formats). */
  readonly text: string
  readonly mimeType?: string
  readonly byteSize?: number
  readonly provenance?: DocumentProvenance
  readonly nowMs?: number
  /** Max stored extracted chars (default 100_000). */
  readonly maxExtractedChars?: number
  /** Max accepted input chars before truncate (default 500_000). */
  readonly maxInputChars?: number
}

export type DocumentValidation =
  | { readonly ok: true; readonly value: DocumentRecord }
  | { readonly ok: false; readonly reason: string }

export const DOCUMENT_FORMATS: readonly DocumentFormat[] = ["plaintext", "markdown", "pdf"]

export function defaultMimeForFormat(format: DocumentFormat): string {
  switch (format) {
    case "markdown":
      return "text/markdown"
    case "pdf":
      return "application/pdf"
    default:
      return "text/plain"
  }
}

export function parseDocumentFormat(raw: string): DocumentFormat | null {
  const v = raw.trim().toLowerCase()
  if (v === "text" || v === "plaintext" || v === "txt") return "plaintext"
  if (v === "md" || v === "markdown") return "markdown"
  if (v === "pdf") return "pdf"
  return null
}

/**
 * Build a DocumentRecord from Owner-provided text.
 * `pdf` requires pre-extracted text (no embedded PDF parser in MVP).
 */
export function ingestDocumentRecord(input: IngestDocumentInput): DocumentValidation {
  const subject = input.subject.trim()
  const title = input.title.trim()
  if (!subject) return { ok: false, reason: "subject is required" }
  if (!title) return { ok: false, reason: "title is required" }
  if (!DOCUMENT_FORMATS.includes(input.format)) {
    return { ok: false, reason: "unsupported format" }
  }

  const maxInput = input.maxInputChars ?? 500_000
  const maxExtracted = input.maxExtractedChars ?? 100_000
  const rawText = typeof input.text === "string" ? input.text : ""
  if (!rawText.trim()) {
    return {
      ok: false,
      reason:
        input.format === "pdf"
          ? "pdf ingest requires pre-extracted text (binary PDF parse not in MVP)"
          : "text is required",
    }
  }
  if (rawText.length > maxInput) {
    return { ok: false, reason: `text exceeds maxInputChars (${maxInput})` }
  }

  const nowMs = input.nowMs ?? Date.now()
  const extractedText =
    rawText.length > maxExtracted ? `${rawText.slice(0, maxExtracted)}\n…[truncated]` : rawText
  const byteSize =
    typeof input.byteSize === "number" && Number.isFinite(input.byteSize) && input.byteSize >= 0
      ? Math.floor(input.byteSize)
      : Buffer.byteLength(rawText, "utf8")

  return {
    ok: true,
    value: {
      id: (input.id ?? crypto.randomUUID()).trim(),
      subject,
      title,
      format: input.format,
      mimeType: (input.mimeType ?? defaultMimeForFormat(input.format)).trim(),
      byteSize,
      extractedText,
      status: "ready",
      failureReason: null,
      provenance: input.provenance ?? {},
      createdAt: nowMs,
      updatedAt: nowMs,
    },
  }
}

/**
 * 文档级粗筛：任一词项命中即可进入块级打分。
 *
 * 之前直接 `includes(整串查询)`，模型把查询改写成「差旅 住宿」这类空格分词
 * 形式时会 0 命中；块级 `scoreRecallText` 已按词项覆盖率排序，粗筛用 OR
 * 不会降低精度，只避免改写后的查询被整串匹配挡掉。
 */
export function matchDocumentQuery(record: DocumentRecord, query: string): boolean {
  const terms = tokenizeRecallQuery(query)
  if (terms.length === 0) return true
  const hay =
    `${record.title}\n${record.extractedText}\n${record.provenance.note ?? ""}`.toLowerCase()
  return terms.some((term) => hay.includes(term))
}

export function selectDocumentsForRecall(input: {
  readonly records: readonly DocumentRecord[]
  readonly query?: string
  readonly limit?: number
}): readonly DocumentRecord[] {
  const limit = input.limit ?? 5
  return input.records
    .filter((r) => r.status === "ready")
    .filter((r) => matchDocumentQuery(r, input.query ?? ""))
    .sort((a, b) => b.updatedAt - a.updatedAt)
    .slice(0, Math.max(0, limit))
}

/** Snippet for tool / prompt (not full dump). */
export function formatDocumentSnippet(record: DocumentRecord, maxChars = 800): string {
  const body =
    record.extractedText.length <= maxChars
      ? record.extractedText
      : `${record.extractedText.slice(0, maxChars - 3)}...`
  return `[doc:${record.id.slice(0, 8)} ${record.format}] ${record.title}\n${body}`
}

// ── Chunk-level retrieval (Ragas context precision / citation) ──

export interface DocumentChunk {
  readonly docId: DocumentId
  /** Stable citation id: `<docId>#<index>`. */
  readonly chunkId: string
  readonly index: number
  readonly start: number
  readonly end: number
  readonly text: string
}

export interface ScoredDocumentChunk {
  readonly chunk: DocumentChunk
  readonly title: string
  readonly format: DocumentFormat
  /** 0..1：纯词法覆盖率，或 hybrid 加权分。 */
  readonly score: number
  readonly scoreKind: "lexical" | "hybrid"
  /** 0..1 cosine；无 embedding 时缺省。 */
  readonly semanticScore?: number
  readonly matchedTerms: readonly string[]
}

/** hybrid 检索所需的向量；纯函数，不在 domain 内发网络请求。 */
export interface ChunkEmbeddingLookup {
  readonly queryEmbedding: readonly number[]
  readonly chunkEmbedding: (chunk: DocumentChunk) => readonly number[] | undefined
  /** 词法权重，默认 0.5。 */
  readonly lexicalWeight?: number
  /** hybrid 模式最低分，默认 0.05。 */
  readonly minScore?: number
}

export function cosineSimilarity(a: readonly number[], b: readonly number[]): number {
  if (a.length === 0 || a.length !== b.length) return 0
  let dot = 0
  let normA = 0
  let normB = 0
  for (let i = 0; i < a.length; i += 1) {
    const x = a[i] ?? 0
    const y = b[i] ?? 0
    dot += x * y
    normA += x * x
    normB += y * y
  }
  if (normA === 0 || normB === 0) return 0
  return dot / (Math.sqrt(normA) * Math.sqrt(normB))
}

/**
 * 按字符窗口切块；优先在段落边界断开，避免把句子切碎。
 * 这是轻量 chunker，不调用 embedding，也不改变原文。
 */
export function chunkDocumentText(
  text: string,
  options: { readonly maxChars?: number; readonly overlap?: number } = {},
): readonly DocumentChunk[] {
  const maxChars = Math.max(120, options.maxChars ?? 800)
  const overlap = Math.max(0, Math.min(options.overlap ?? 80, Math.floor(maxChars / 2)))
  if (!text) return []
  const chunks: DocumentChunk[] = []
  let start = 0
  while (start < text.length) {
    let end = Math.min(start + maxChars, text.length)
    if (end < text.length) {
      const breakAt = text.lastIndexOf("\n", end)
      if (breakAt > start + Math.floor(maxChars / 2)) end = breakAt + 1
    }
    const body = text.slice(start, end).trim()
    if (body) {
      chunks.push({ docId: "", chunkId: "", index: chunks.length, start, end, text: body })
    }
    if (end >= text.length) break
    start = Math.max(end - overlap, start + 1)
  }
  return chunks
}

/** 把查询拆成词项；中文额外生成 bigram，避免整句匹配不到。 */
export function tokenizeRecallQuery(query: string): readonly string[] {
  const q = query.trim().toLowerCase()
  if (!q) return []
  const parts = q.split(/[\s,，。.!！?？;；:：、/\\|()（）[\]{}"'“”‘’_-]+/).filter(Boolean)
  const terms = new Set<string>(parts)
  for (const part of parts) {
    if (part.length >= 2 && /[\u4e00-\u9fff]/.test(part)) {
      for (let i = 0; i < part.length - 1; i += 1) terms.add(part.slice(i, i + 2))
    }
  }
  return [...terms]
}

/** 词项覆盖率；返回 0..1 与命中词，便于评估解释。 */
export function scoreRecallText(
  query: string,
  text: string,
): { readonly score: number; readonly matchedTerms: readonly string[] } {
  const terms = tokenizeRecallQuery(query)
  if (terms.length === 0) return { score: 0, matchedTerms: [] }
  const haystack = text.toLowerCase()
  const matched = terms.filter((term) => haystack.includes(term))
  return { score: matched.length / terms.length, matchedTerms: matched }
}

/**
 * 文档级 → 块级召回：先按文档过滤，再在文档内切块打分。
 * 无 query 时保留时间排序，score 为 0。
 *
 * 提供 embedding 时进入 hybrid 模式：不做子串预过滤（否则改写提问会被
 * 直接过滤掉），而是对所有 ready 文档的块做词法 + cosine 加权。
 */
export function selectDocumentChunksForRecall(input: {
  readonly records: readonly DocumentRecord[]
  readonly query?: string
  readonly limit?: number
  readonly chunkLimitPerDoc?: number
  readonly chunkChars?: number
  readonly embedding?: ChunkEmbeddingLookup
}): readonly ScoredDocumentChunk[] {
  const limit = Math.max(0, input.limit ?? 5)
  const perDoc = Math.max(1, input.chunkLimitPerDoc ?? 3)
  const query = input.query ?? ""
  const embedding = input.embedding
  const semantic = embedding !== undefined && query.trim().length > 0
  const docs = selectDocumentsForRecall({
    records: input.records,
    query: semantic ? "" : query,
    limit: input.records.length,
  })
  const hits: ScoredDocumentChunk[] = []
  // 标题命中作为同分时的排序权重：正文同覆盖率时，标题含查询词的文档更可能是
  // 目标（如「payments-api 部署手册」优于在正文顺带提到端口的网关说明书）。
  const titleScores = new Map<string, number>()
  for (const record of docs) {
    const chunks = chunkDocumentText(record.extractedText, { maxChars: input.chunkChars })
    const titleCoverage = query.trim() ? scoreRecallText(query, record.title).score : 0
    const scored = chunks
      .map((chunk) => {
        const withIds: DocumentChunk = {
          ...chunk,
          docId: record.id,
          chunkId: `${record.id}#${chunk.index}`,
        }
        titleScores.set(withIds.chunkId, titleCoverage)
        const lexical = scoreRecallText(query, `${record.title}\n${chunk.text}`)
        let score = lexical.score
        let semanticScore: number | undefined
        if (semantic) {
          const vector = embedding.chunkEmbedding(withIds)
          if (vector && vector.length === embedding.queryEmbedding.length) {
            const cosine = cosineSimilarity(embedding.queryEmbedding, vector)
            semanticScore = Math.max(0, cosine)
            const weight = embedding.lexicalWeight ?? 0.5
            score = weight * lexical.score + (1 - weight) * semanticScore
          }
        }
        return {
          chunk: withIds,
          title: record.title,
          format: record.format,
          score,
          scoreKind: semanticScore === undefined ? ("lexical" as const) : ("hybrid" as const),
          ...(semanticScore === undefined ? {} : { semanticScore }),
          matchedTerms: lexical.matchedTerms,
        }
      })
      .filter((hit) => {
        if (!semantic) {
          // 纯词法模式只保留真正命中的块：查询非空时丢弃 0 覆盖率的块，
          // 否则会把不相关文档按时间顺序当成“命中”返回。
          return query.trim().length === 0 || hit.matchedTerms.length > 0
        }
        const minScore = embedding?.minScore ?? 0.05
        return hit.score >= minScore || hit.matchedTerms.length > 0
      })
      .sort(
        (a, b) =>
          b.score - a.score ||
          (titleScores.get(b.chunk.chunkId) ?? 0) - (titleScores.get(a.chunk.chunkId) ?? 0) ||
          a.chunk.index - b.chunk.index,
      )
      .slice(0, perDoc)
    hits.push(...scored)
  }
  if (query.trim()) {
    hits.sort(
      (a, b) =>
        b.score - a.score ||
        (titleScores.get(b.chunk.chunkId) ?? 0) - (titleScores.get(a.chunk.chunkId) ?? 0),
    )
  }
  return hits.slice(0, limit)
}

/** 带 citation 的块片段；引用 id 可直接用于 Ragas / 人工核对。 */
export function formatChunkSnippet(hit: ScoredDocumentChunk, maxChars = 800): string {
  const body =
    hit.chunk.text.length <= maxChars
      ? hit.chunk.text
      : `${hit.chunk.text.slice(0, maxChars - 3)}...`
  return `[doc:${hit.chunk.docId.slice(0, 8)}#${hit.chunk.index} ${hit.format} score=${hit.score.toFixed(2)}] ${hit.title}\n${body}`
}

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

export function matchDocumentQuery(record: DocumentRecord, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  const hay = `${record.title}\n${record.extractedText}\n${record.provenance.note ?? ""}`.toLowerCase()
  return hay.includes(q)
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

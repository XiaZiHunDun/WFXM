/**
 * Project Knowledge — layer 3 (DESIGN §9).
 * Project-scoped notes and file snapshots; not Durable Memory; not Transcript.
 */
import type { DocumentRecord } from "./document-ingest.js"

export type ProjectKnowledgeId = string

export type ProjectKnowledgeKind =
  | "file_snapshot"
  | "memory_md"
  | "manual_note"
  | "ingested_document"

export const PROJECT_KNOWLEDGE_KINDS: readonly ProjectKnowledgeKind[] = [
  "file_snapshot",
  "memory_md",
  "manual_note",
  "ingested_document",
]

export interface ProjectKnowledgeProvenance {
  readonly conversationId?: string
  readonly messageId?: string
  readonly documentId?: string
  readonly sourcePath?: string
  readonly sourceMtimeMs?: number
  readonly sourceSize?: number
  readonly note?: string
}

export interface ProjectKnowledgeRecord {
  readonly id: ProjectKnowledgeId
  readonly projectId: string
  readonly title: string
  readonly kind: ProjectKnowledgeKind
  readonly body: string
  readonly byteSize: number
  readonly provenance: ProjectKnowledgeProvenance
  readonly createdAt: number
  readonly updatedAt: number
}

export interface CreateProjectKnowledgeInput {
  readonly id?: string
  readonly projectId: string
  readonly title: string
  readonly kind: ProjectKnowledgeKind
  readonly body: string
  readonly provenance?: ProjectKnowledgeProvenance
  readonly nowMs?: number
  readonly maxBodyChars?: number
}

export type ProjectKnowledgeValidation =
  | { readonly ok: true; readonly value: ProjectKnowledgeRecord }
  | { readonly ok: false; readonly reason: string }

export function normalizeProjectId(projectId: string): string {
  return projectId.trim()
}

export function createProjectKnowledgeRecord(
  input: CreateProjectKnowledgeInput,
): ProjectKnowledgeValidation {
  const projectId = normalizeProjectId(input.projectId)
  const title = input.title.trim()
  const bodyRaw = typeof input.body === "string" ? input.body : ""
  if (!projectId) return { ok: false, reason: "projectId is required" }
  if (!title) return { ok: false, reason: "title is required" }
  if (!PROJECT_KNOWLEDGE_KINDS.includes(input.kind)) {
    return { ok: false, reason: "invalid kind" }
  }
  if (!bodyRaw.trim()) return { ok: false, reason: "body is required" }

  const maxBody = input.maxBodyChars ?? 100_000
  if (bodyRaw.length > maxBody) {
    return { ok: false, reason: `body exceeds maxBodyChars (${maxBody})` }
  }

  const nowMs = input.nowMs ?? Date.now()
  const body =
    bodyRaw.length > maxBody ? `${bodyRaw.slice(0, maxBody)}\n…[truncated]` : bodyRaw

  return {
    ok: true,
    value: {
      id: (input.id ?? crypto.randomUUID()).trim(),
      projectId,
      title,
      kind: input.kind,
      body,
      byteSize: Buffer.byteLength(body, "utf8"),
      provenance: input.provenance ?? {},
      createdAt: nowMs,
      updatedAt: nowMs,
    },
  }
}

export function projectKnowledgeFromDocument(input: {
  readonly projectId: string
  readonly document: DocumentRecord
  readonly title?: string
  readonly nowMs?: number
}): ProjectKnowledgeValidation {
  if (input.document.status !== "ready") {
    return { ok: false, reason: "document is not ready" }
  }
  return createProjectKnowledgeRecord({
    projectId: input.projectId,
    title: input.title?.trim() || input.document.title,
    kind: "ingested_document",
    body: input.document.extractedText,
    provenance: {
      documentId: input.document.id,
      ...(input.document.provenance.sourcePath
        ? { sourcePath: input.document.provenance.sourcePath }
        : {}),
      note: `promoted from document ${input.document.title}`,
    },
    nowMs: input.nowMs,
  })
}

export function matchProjectKnowledgeQuery(record: ProjectKnowledgeRecord, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  const hay = `${record.title}\n${record.body}\n${record.provenance.note ?? ""}\n${record.provenance.sourcePath ?? ""}`.toLowerCase()
  return hay.includes(q)
}

export function selectProjectKnowledgeForRecall(input: {
  readonly records: readonly ProjectKnowledgeRecord[]
  readonly query?: string
  readonly limit?: number
}): readonly ProjectKnowledgeRecord[] {
  const limit = input.limit ?? 5
  return input.records
    .filter((r) => matchProjectKnowledgeQuery(r, input.query ?? ""))
    .sort((a, b) => b.updatedAt - a.updatedAt)
    .slice(0, Math.max(0, limit))
}

export function formatProjectKnowledgeSnippet(record: ProjectKnowledgeRecord, maxChars = 800): string {
  const body =
    record.body.length <= maxChars ? record.body : `${record.body.slice(0, maxChars)}…`
  const path = record.provenance.sourcePath ? ` path=${record.provenance.sourcePath}` : ""
  return `[${record.kind}] ${record.title}${path}\n${body}`
}

export function formatProjectKnowledgePrefix(
  records: readonly ProjectKnowledgeRecord[],
): string | null {
  if (records.length === 0) return null
  const lines = records.map(
    (r, i) => `${i + 1}. ${formatProjectKnowledgeSnippet(r, 400)}`,
  )
  return `Project Knowledge (confirmed ingest, substring recall):\n${lines.join("\n\n")}`
}

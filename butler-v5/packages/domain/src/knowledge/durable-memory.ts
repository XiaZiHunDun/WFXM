/**
 * Durable Memory — layer 2 knowledge (DESIGN §9).
 * Not Transcript; not Project Knowledge; never auto-upgraded from Run compaction.
 */

export type DurableMemoryId = string

export type DurableMemorySourceKind = "owner" | "message" | "document"

export type DurableMemoryStatus = "candidate" | "confirmed" | "rejected" | "expired"

export type DurableMemoryPromotedBy = "owner" | "sweeper"

export interface DurableMemoryProvenance {
  readonly conversationId?: string
  readonly messageId?: string
  readonly documentId?: string
  readonly note?: string
}

export interface DurableMemoryRecord {
  readonly id: DurableMemoryId
  readonly subject: string
  readonly content: string
  readonly sourceKind: DurableMemorySourceKind
  readonly status: DurableMemoryStatus
  /** 0..1 */
  readonly confidence: number
  readonly provenance: DurableMemoryProvenance
  readonly expiresAt: number | null
  readonly createdAt: number
  readonly updatedAt: number
  readonly confirmedAt: number | null
  // D42 §12 G4 auto-promote (append-only; see migration 0012 + persistence/schema.ts).
  /** Who promoted this record to confirmed. 'owner' for owner-confirmed; 'sweeper' for sweeper-auto-promoted; null for non-confirmed. */
  readonly promotedBy: DurableMemoryPromotedBy | null
  /** When sweeper auto-promoted this record (ms epoch). NULL for owner-confirmed or non-confirmed. */
  readonly promotedAt: number | null
  /** Owner who rolled back this auto-promoted record. NULL if never rolled back. */
  readonly rolledBackBy: string | null
  /** When owner rolled back this auto-promoted record (ms epoch). NULL if never rolled back. */
  readonly rolledBackAt: number | null
  /** Owner-provided reason for rollback. NULL if no reason provided. */
  readonly rollbackReason: string | null
}

export interface CreateDurableMemoryInput {
  readonly id?: string
  readonly subject: string
  readonly content: string
  readonly sourceKind: DurableMemorySourceKind
  /** Owner-authored defaults to confirmed; model-proposed must be candidate. */
  readonly status?: DurableMemoryStatus
  readonly confidence?: number
  readonly provenance?: DurableMemoryProvenance
  readonly expiresAt?: number | null
  readonly nowMs?: number
}

export type DurableMemoryValidation =
  | { readonly ok: true; readonly value: DurableMemoryRecord }
  | { readonly ok: false; readonly reason: string }

export function createDurableMemoryRecord(
  input: CreateDurableMemoryInput,
): DurableMemoryValidation {
  const subject = input.subject.trim()
  const content = input.content.trim()
  if (!subject) return { ok: false, reason: "subject is required" }
  if (!content) return { ok: false, reason: "content is required" }
  if (content.length > 4000) return { ok: false, reason: "content exceeds 4000 chars" }

  const sourceKind = input.sourceKind
  if (sourceKind !== "owner" && sourceKind !== "message" && sourceKind !== "document") {
    return { ok: false, reason: "invalid sourceKind" }
  }

  const status = input.status ?? (sourceKind === "owner" ? "confirmed" : "candidate")
  if (status !== "candidate" && status !== "confirmed" && status !== "rejected") {
    return { ok: false, reason: "invalid status" }
  }

  const confidence =
    input.confidence === undefined ? (status === "confirmed" ? 1 : 0.5) : input.confidence
  if (!Number.isFinite(confidence) || confidence < 0 || confidence > 1) {
    return { ok: false, reason: "confidence must be between 0 and 1" }
  }

  const nowMs = input.nowMs ?? Date.now()
  const expiresAt = input.expiresAt === undefined ? null : input.expiresAt
  if (expiresAt !== null && (!Number.isFinite(expiresAt) || expiresAt <= nowMs)) {
    return { ok: false, reason: "expiresAt must be in the future when set" }
  }

  const provenance = input.provenance ?? {}
  if (sourceKind === "message" && !provenance.messageId?.trim()) {
    return { ok: false, reason: "message provenance requires messageId" }
  }
  if (sourceKind === "document" && !provenance.documentId?.trim()) {
    return { ok: false, reason: "document provenance requires documentId" }
  }

  return {
    ok: true,
    value: {
      id: (input.id ?? crypto.randomUUID()).trim(),
      subject,
      content,
      sourceKind,
      status,
      confidence,
      provenance,
      expiresAt,
      createdAt: nowMs,
      updatedAt: nowMs,
      confirmedAt: status === "confirmed" ? nowMs : null,
      promotedBy: null,
      promotedAt: null,
      rolledBackBy: null,
      rolledBackAt: null,
      rollbackReason: null,
    },
  }
}

export function isDurableMemoryActive(
  record: DurableMemoryRecord,
  nowMs: number,
): boolean {
  if (record.status !== "confirmed") return false
  if (record.expiresAt !== null && record.expiresAt <= nowMs) return false
  return true
}

/** Case-insensitive substring search over content + provenance note. */
export function matchDurableMemoryQuery(
  record: DurableMemoryRecord,
  query: string,
): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  const hay = `${record.content}\n${record.provenance.note ?? ""}`.toLowerCase()
  return hay.includes(q)
}

export function selectDurableMemoriesForWorkingSet(input: {
  readonly records: readonly DurableMemoryRecord[]
  readonly nowMs: number
  readonly query?: string
  readonly limit?: number
}): readonly DurableMemoryRecord[] {
  const limit = input.limit ?? 8
  const matched = input.records
    .filter((r) => isDurableMemoryActive(r, input.nowMs))
    .filter((r) => matchDurableMemoryQuery(r, input.query ?? ""))
    .sort((a, b) => b.updatedAt - a.updatedAt)
  return matched.slice(0, Math.max(0, limit))
}

/** Format selected memories as a system prefix block (not Transcript). */
export function formatDurableMemoryPrefix(
  records: readonly DurableMemoryRecord[],
): string | null {
  if (records.length === 0) return null
  const lines = records.map((r) => {
    const conf = Math.round(r.confidence * 100)
    return `- [${r.id.slice(0, 8)} conf=${conf}% src=${r.sourceKind}] ${r.content}`
  })
  return `Durable Memory (confirmed facts/preferences; not conversation transcript):\n${lines.join("\n")}`
}

export function confirmDurableMemory(
  record: DurableMemoryRecord,
  nowMs: number,
): DurableMemoryRecord {
  return {
    ...record,
    status: "confirmed",
    confidence: Math.max(record.confidence, 0.8),
    updatedAt: nowMs,
    confirmedAt: nowMs,
    // D42 §12 G4 follow-up: owner 显式 confirm 必须标 promotedBy='owner'，
    // 否则与 sweeper 自动 promote 无法区分（rollback-auto-promote 依赖此判别字段）。
    promotedBy: "owner",
  }
}

export function rejectDurableMemory(
  record: DurableMemoryRecord,
  nowMs: number,
): DurableMemoryRecord {
  return {
    ...record,
    status: "rejected",
    updatedAt: nowMs,
    confirmedAt: null,
  }
}

/**
 * D65 T2c — Extract `documents/:documentId/promote-memory` handler from documents.ts.
 *
 * Document→memory promotion with G2 dedup guard (D41 T4) and §13 audit row.
 * Subject is doc.subject (the document owner), not the calling owner — dedup
 * is per-owner memory. Operator log on dedup hit so the failure isn't silent.
 *
 * Behavior unchanged from original inline handler.
 */
import type { Context } from "hono"
import { createDurableMemoryRecord } from "@butler/domain/knowledge/durable-memory.js"
import type { Wiring } from "../wiring.js"
import { ownerAuthorized } from "../owner-auth.js"
import type { makeDedupChecker } from "./memory-dedup.js"
import { unauthorizedForOwner } from "../owner-jargon.js"

export async function handlePromoteMemory(
  c: Context,
  wiring: Wiring,
  checkDedup: ReturnType<typeof makeDedupChecker>,
): Promise<Response> {
  if (!ownerAuthorized(c)) return unauthorizedForOwner(c)
  const docs = wiring.documentStore
  const memories = wiring.durableMemoryStore
  if (!docs || !memories) {
    return c.json({ ok: false, reason: "document or memory store unavailable" }, 503)
  }
  // Route param is guaranteed by the registered route path
  // `/v1/owner/documents/:documentId/promote-memory`. `?? ""` mirrors
  // memories-rollback.ts (T2a) and tasks-run.ts (T2b) because the extracted
  // Context type loses Hono's route narrowing that the inline closure had.
  const documentId = c.req.param("documentId") ?? ""
  const doc = await docs.get(documentId)
  if (!doc) return c.json({ ok: false, reason: "未找到对应记录" }, 404)
  const body = (await c.req.json().catch(() => ({}))) as {
    readonly content?: string
    readonly status?: string
    readonly force?: boolean
  }
  const content =
    (typeof body.content === "string" && body.content.trim()
      ? body.content.trim()
      : `${doc.title}: ${doc.extractedText}`
    ).slice(0, 4000)
  const created = createDurableMemoryRecord({
    subject: doc.subject,
    content,
    sourceKind: "document",
    status:
      body.status === "confirmed" || body.status === "candidate" ? body.status : "candidate",
    provenance: {
      documentId: doc.id,
      ...(doc.provenance.conversationId
        ? { conversationId: doc.provenance.conversationId }
        : {}),
      note: `promoted from document ${doc.title}`,
    },
  })
  if (!created.ok) return c.json({ ok: false, reason: created.reason }, 400)
  // G2 dedup guard (D41 T4): same threshold + force semantics as
  // POST /v1/owner/memories. Subject is doc.subject (the document owner),
  // not the calling owner — dedup is per-owner memory.
  const dedupHit = await checkDedup({
    store: memories,
    subject: created.value.subject,
    content: created.value.content,
    force: body.force === true,
  })
  if (dedupHit !== null) {
    // eslint-disable-next-line no-console -- operator log when no logger injected
    console.error(
      `[memory-dedup] hit (promote-memory) existingId=${dedupHit.existingMemoryId} similarity=${dedupHit.similarity.toFixed(3)} status=${dedupHit.status}`,
    )
    return c.json(
      {
        ok: false,
        reason: "duplicate",
        existingMemoryId: dedupHit.existingMemoryId,
        similarity: dedupHit.similarity,
        status: dedupHit.status,
      },
      409,
    )
  }
  const saved = await memories.create(created.value)
  // D59 T1 (audit #1 F-21): §13 audit completeness — document→memory
  // promotion mutates durable memory state; mirror mcp.ts revoke-grants.
  await wiring.runtimeStore.appendAuditEvent({
    auditId: crypto.randomUUID(),
    runId: null,
    conversationId: null,
    action: "memory.created_from_document",
    subject: created.value.subject,
    detail: { memoryId: saved.id, documentId: doc.id },
    createdAt: new Date(),
  })
  return c.json({ ok: true, item: saved })
}

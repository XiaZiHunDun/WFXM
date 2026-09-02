import type { Hono } from "hono"
import {
  ingestDocumentRecord,
  parseDocumentFormat,
} from "@butler/domain/knowledge/document-ingest.js"
import { createDurableMemoryRecord } from "@butler/domain/knowledge/durable-memory.js"
import { projectKnowledgeFromDocument } from "@butler/domain/knowledge/project-knowledge.js"
import type { Wiring } from "../wiring.js"
import { ownerAuthorized } from "../owner-auth.js"
import { makeDedupChecker } from "./memory-dedup.js"

/**
 * Owner control-surface routes for documents, including document→memory and
 * document→project-knowledge promotion plus cascade delete.
 * Split from owner-routes.ts (file-size gate) — behavior unchanged.
 */
export function registerDocumentsRoutes(app: Hono, wiring: Wiring): void {
  // G2 dedup guard shared with the memories routes (module-scoped config).
  const checkDedup = makeDedupChecker()

  app.get("/v1/owner/documents", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.documentStore
    if (!store) return c.json({ ok: false, reason: "document store unavailable" }, 503)
    const subject = (c.req.query("subject") ?? "owner").trim() || "owner"
    const items = await store.listBySubject({ subject, limit: 100 })
    return c.json({
      items: items.map((d) => ({
        ...d,
        extractedText:
          d.extractedText.length > 500
            ? `${d.extractedText.slice(0, 500)}…`
            : d.extractedText,
      })),
    })
  })

  app.get("/v1/owner/documents/:documentId", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.documentStore
    if (!store) return c.json({ ok: false, reason: "document store unavailable" }, 503)
    const item = await store.get(c.req.param("documentId"))
    if (!item) return c.json({ ok: false, reason: "not found" }, 404)
    return c.json({ ok: true, item })
  })

  app.post("/v1/owner/documents", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.documentStore
    if (!store) return c.json({ ok: false, reason: "document store unavailable" }, 503)
    const body = (await c.req.json().catch(() => ({}))) as {
      readonly subject?: string
      readonly title?: string
      readonly format?: string
      readonly text?: string
      readonly mimeType?: string
      readonly byteSize?: number
      readonly provenance?: Record<string, unknown>
    }
    const format = parseDocumentFormat(body.format ?? "plaintext")
    if (!format) {
      return c.json(
        { ok: false, reason: "unsupported format (plaintext|markdown|pdf)" },
        400,
      )
    }
    const created = ingestDocumentRecord({
      subject: body.subject ?? "owner",
      title: body.title ?? "",
      format,
      text: body.text ?? "",
      ...(typeof body.mimeType === "string" ? { mimeType: body.mimeType } : {}),
      ...(typeof body.byteSize === "number" ? { byteSize: body.byteSize } : {}),
      ...(body.provenance
        ? {
            provenance: {
              ...(typeof body.provenance["conversationId"] === "string"
                ? { conversationId: body.provenance["conversationId"] }
                : {}),
              ...(typeof body.provenance["messageId"] === "string"
                ? { messageId: body.provenance["messageId"] }
                : {}),
              ...(typeof body.provenance["sourcePath"] === "string"
                ? { sourcePath: body.provenance["sourcePath"] }
                : {}),
              ...(typeof body.provenance["note"] === "string"
                ? { note: body.provenance["note"] }
                : {}),
            },
          }
        : {}),
    })
    if (!created.ok) return c.json({ ok: false, reason: created.reason }, 400)
    const saved = await store.create(created.value)
    return c.json({ ok: true, item: saved })
  })

  app.post("/v1/owner/documents/:documentId/promote-memory", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const docs = wiring.documentStore
    const memories = wiring.durableMemoryStore
    if (!docs || !memories) {
      return c.json({ ok: false, reason: "document or memory store unavailable" }, 503)
    }
    const documentId = c.req.param("documentId")
    const doc = await docs.get(documentId)
    if (!doc) return c.json({ ok: false, reason: "not found" }, 404)
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
    return c.json({ ok: true, item: saved })
  })

  app.post("/v1/owner/documents/:documentId/promote-project-knowledge", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const docs = wiring.documentStore
    const pk = wiring.projectKnowledgeStore
    if (!docs || !pk) {
      return c.json({ ok: false, reason: "document or project knowledge store unavailable" }, 503)
    }
    const documentId = c.req.param("documentId")
    const doc = await docs.get(documentId)
    if (!doc) return c.json({ ok: false, reason: "not found" }, 404)
    const body = (await c.req.json().catch(() => ({}))) as {
      readonly projectId?: string
      readonly title?: string
    }
    const projectId = (body.projectId ?? c.req.query("projectId") ?? "").trim()
    if (!projectId) return c.json({ ok: false, reason: "projectId is required" }, 400)
    const created = projectKnowledgeFromDocument({
      projectId,
      document: doc,
      ...(typeof body.title === "string" && body.title.trim() ? { title: body.title } : {}),
    })
    if (!created.ok) return c.json({ ok: false, reason: created.reason }, 400)
    const saved = await pk.create(created.value)
    return c.json({ ok: true, item: saved })
  })

  app.delete("/v1/owner/documents/:documentId", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.documentStore
    if (!store) return c.json({ ok: false, reason: "document store unavailable" }, 503)
    const documentId = c.req.param("documentId")
    const ok = await store.delete(documentId)
    if (!ok) return c.json({ ok: false, reason: "not found" }, 404)
    const cascaded =
      (await wiring.durableMemoryStore?.deleteBySourceDocumentId(documentId)) ?? 0
    const cascadedProjectKnowledge =
      (await wiring.projectKnowledgeStore?.deleteBySourceDocumentId(documentId)) ?? 0
    return c.json({
      ok: true,
      documentId,
      cascadedMemories: cascaded,
      cascadedProjectKnowledge,
    })
  })
}

import type { Hono } from "hono"
import {
  confirmDurableMemory,
  createDurableMemoryRecord,
  rejectDurableMemory,
  type DurableMemoryRecord,
  type DurableMemoryStatus,
} from "@butler/domain/knowledge/durable-memory.js"
import { rollbackAutoPromotedCandidate } from "@butler/domain/knowledge/auto-promote.js"
import type { DurableMemoryStore } from "@butler/persistence"
import { parseAutoPromoteConfig } from "../auto-promote-config.js"
import type { Wiring } from "../wiring.js"
import { ownerAuthorized } from "../owner-auth.js"
import { makeDedupChecker } from "./memory-dedup.js"

/**
 * Owner control-surface routes for durable memories, including batch
 * confirm/reject helpers and G2 dedup / G4 auto-promote rollback guards.
 * Split from owner-routes.ts (file-size gate) — behavior unchanged.
 */
export function registerMemoriesRoutes(app: Hono, wiring: Wiring): void {
  app.get("/v1/owner/memories", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.durableMemoryStore
    if (!store) return c.json({ ok: false, reason: "durable memory store unavailable" }, 503)
    const subject = (c.req.query("subject") ?? "owner").trim() || "owner"
    const statusRaw = (c.req.query("status") ?? "").trim()
    const status: DurableMemoryStatus | undefined =
      statusRaw === "candidate" || statusRaw === "confirmed" || statusRaw === "rejected" || statusRaw === "expired"
        ? statusRaw
        : undefined
    if (statusRaw && !status) {
      return c.json({ ok: false, reason: "invalid status (must be candidate|confirmed|rejected|expired)" }, 400)
    }
    const limitRaw = c.req.query("limit")
    const limit = limitRaw ? Number.parseInt(limitRaw, 10) : 20
    if (!Number.isFinite(limit) || limit < 1 || limit > 100) {
      return c.json({ ok: false, reason: "invalid limit (1-100, default 20)" }, 400)
    }
    const offsetRaw = c.req.query("offset")
    const offset = offsetRaw ? Number.parseInt(offsetRaw, 10) : 0
    if (!Number.isFinite(offset) || offset < 0) {
      return c.json({ ok: false, reason: "invalid offset (>=0, default 0)" }, 400)
    }

    const items = await store.listBySubject({
      subject,
      ...(status ? { status } : {}),
      limit,
      offset,
    })
    const total = await store.countBySubject({
      subject,
      ...(status ? { status } : {}),
    })
    return c.json({
      items,
      total,
      hasMore: offset + items.length < total,
    })
  })

  app.post("/v1/owner/memories", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.durableMemoryStore
    if (!store) return c.json({ ok: false, reason: "durable memory store unavailable" }, 503)
    const body = (await c.req.json().catch(() => ({}))) as {
      readonly subject?: string
      readonly content?: string
      readonly sourceKind?: string
      readonly status?: string
      readonly confidence?: number
      readonly provenance?: Record<string, unknown>
      readonly expiresAt?: number | null
      readonly force?: boolean
    }
    const sourceKind =
      body.sourceKind === "message" || body.sourceKind === "document" ? body.sourceKind : "owner"
    const created = createDurableMemoryRecord({
      subject: body.subject ?? "owner",
      content: body.content ?? "",
      sourceKind,
      ...(body.status === "candidate" || body.status === "confirmed" || body.status === "rejected"
        ? { status: body.status }
        : {}),
      ...(typeof body.confidence === "number" ? { confidence: body.confidence } : {}),
      ...(body.provenance
        ? {
            provenance: {
              ...(typeof body.provenance["conversationId"] === "string"
                ? { conversationId: body.provenance["conversationId"] }
                : {}),
              ...(typeof body.provenance["messageId"] === "string"
                ? { messageId: body.provenance["messageId"] }
                : {}),
              ...(typeof body.provenance["documentId"] === "string"
                ? { documentId: body.provenance["documentId"] }
                : {}),
              ...(typeof body.provenance["note"] === "string"
                ? { note: body.provenance["note"] }
                : {}),
            },
          }
        : {}),
      ...(body.expiresAt !== undefined ? { expiresAt: body.expiresAt } : {}),
    })
    if (!created.ok) return c.json({ ok: false, reason: created.reason }, 400)
    // G2 dedup guard (D41 T4): block duplicates above threshold unless force=true.
    // Fail-open inside helper — DB errors fall through to create.
    const dedupHit = await checkDedup({
      store,
      subject: created.value.subject,
      content: created.value.content,
      force: body.force === true,
    })
    if (dedupHit !== null) {
      // eslint-disable-next-line no-console -- operator log when no logger injected
      console.error(
        `[memory-dedup] hit subject=${dedupHit.existingMemoryId ? "see-existingMemoryId" : created.value.subject} existingId=${dedupHit.existingMemoryId} similarity=${dedupHit.similarity.toFixed(3)} status=${dedupHit.status}`,
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
    const saved = await store.create(created.value)
    return c.json({ ok: true, item: saved })
  })

  app.post("/v1/owner/memories/:memoryId/confirm", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.durableMemoryStore
    if (!store) return c.json({ ok: false, reason: "durable memory store unavailable" }, 503)
    const memoryId = c.req.param("memoryId")
    const existing = await store.get(memoryId)
    if (!existing) return c.json({ ok: false, reason: "not found" }, 404)
    if (existing.status === "confirmed") {
      return c.json({ ok: false, reason: "already confirmed" }, 409)
    }
    if (existing.status === "expired") {
      return c.json({ ok: false, reason: "already expired" }, 409)
    }
    const updated = await store.update(confirmDurableMemory(existing, Date.now()))
    return c.json({ ok: true, item: updated })
  })

  app.post("/v1/owner/memories/:memoryId/reject", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.durableMemoryStore
    if (!store) return c.json({ ok: false, reason: "durable memory store unavailable" }, 503)
    const memoryId = c.req.param("memoryId")
    const existing = await store.get(memoryId)
    if (!existing) return c.json({ ok: false, reason: "not found" }, 404)
    if (existing.status === "rejected") {
      return c.json({ ok: false, reason: "already rejected" }, 409)
    }
    if (existing.status === "expired") {
      return c.json({ ok: false, reason: "already expired" }, 409)
    }
    const updated = await store.update(rejectDurableMemory(existing, Date.now()))
    return c.json({ ok: true, item: updated })
  })

  // G4: owner rollback for sweeper-auto-promoted records (§12).
  // Owner-driven undo path within the 7d post-promote rollback window.
  // Pure domain validation + audit log on every response (200/404/409).
  // Concurrent modification between validate and UPDATE is handled explicitly:
  // store.rollbackAutoPromoted returns null when WHERE status='confirmed'
  // AND promoted_by='sweeper' no longer matches (e.g. another rollback raced).
  app.post("/v1/owner/memories/:memoryId/rollback-auto-promote", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.durableMemoryStore
    if (!store) return c.json({ ok: false, reason: "durable memory store unavailable" }, 503)
    const memoryId = c.req.param("memoryId")
    const body = (await c.req.json().catch(() => ({}))) as {
      readonly reason?: string
    }
    const now = new Date()

    let memory: Awaited<ReturnType<typeof store.get>> = null
    try {
      memory = await store.get(memoryId)
    } catch (err) {
      // Malformed UUIDs (e.g. "nonexistent") surface as PG syntax errors on
      // the underlying get query; treat those uniformly as "not found" so
      // callers never see driver-level error text (mirrors handleBatch in
      // the batch confirm/reject paths).
      const message = err instanceof Error ? err.message : "unknown error"
      if (message.includes("invalid input syntax for type uuid")) {
        // eslint-disable-next-line no-console -- operator log when no logger injected
        console.error(`[memory-rollback] not-found owner=owner id=${memoryId}`)
        return c.json({ ok: false, reason: "not found" }, 404)
      }
      throw err
    }
    if (memory === null) {
      // eslint-disable-next-line no-console -- operator log when no logger injected
      console.error(`[memory-rollback] not-found owner=owner id=${memoryId}`)
      return c.json({ ok: false, reason: "not found" }, 404)
    }

    // Map store record to domain pure fn input. Type narrow: domain fn requires
    // status='confirmed' & promotedBy='sweeper' literals, but runtime validation
    // handles other cases. We force the literal types to satisfy TS.
    const validation = rollbackAutoPromotedCandidate({
      memory: {
        id: memory.id,
        status: (memory.status === "confirmed" ? "confirmed" : "candidate") as "confirmed",
        promotedBy:
          (memory.promotedBy === "sweeper" ? "sweeper" : "owner") as "sweeper",
        promotedAt:
          memory.promotedAt !== null ? new Date(memory.promotedAt) : new Date(0),
      },
      ownerId: "owner",
      reason: body.reason,
      now,
      rollbackWindowMs: autoPromoteCfg.rollbackWindowMs,
    })

    if (!validation.ok) {
      // eslint-disable-next-line no-console -- operator log when no logger injected
      console.error(
        `[memory-rollback] denied owner=owner id=${memoryId} error=${validation.reason} currentStatus=${memory.status} promotedBy=${memory.promotedBy ?? "null"}`,
      )
      return c.json(
        {
          ok: false,
          error: validation.reason,
          currentStatus: memory.status,
          promotedBy: memory.promotedBy,
          promotedAt:
            memory.promotedAt !== null
              ? new Date(memory.promotedAt).toISOString()
              : null,
          rollbackDeadline:
            memory.promotedAt !== null
              ? new Date(memory.promotedAt + autoPromoteCfg.rollbackWindowMs).toISOString()
              : null,
        },
        409,
      )
    }

    const updated = await store.rollbackAutoPromoted({
      id: memoryId,
      ownerId: "owner",
      reason: body.reason,
      now,
    })

    if (updated === null) {
      // Concurrent race: between validation and UPDATE, status/promoted_by changed
      // (e.g. another rollback won, or owner-confirmed path raced).
      // eslint-disable-next-line no-console -- operator log when no logger injected
      console.error(`[memory-rollback] concurrent-modification owner=owner id=${memoryId}`)
      return c.json({ ok: false, error: "concurrent-modification" }, 409)
    }

    // eslint-disable-next-line no-console -- operator log when no logger injected
    console.error(
      `[memory-rollback] ok owner=owner id=${memoryId} reason=${body.reason ?? "none"}`,
    )
    return c.json({ memory: updated })
  })

  app.delete("/v1/owner/memories/:memoryId", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.durableMemoryStore
    if (!store) return c.json({ ok: false, reason: "durable memory store unavailable" }, 503)
    const memoryId = c.req.param("memoryId")
    const ok = await store.delete(memoryId)
    if (!ok) return c.json({ ok: false, reason: "not found" }, 404)
    return c.json({ ok: true, memoryId })
  })

  function parseBatchIds(
    body: unknown,
  ):
    | { readonly ok: true; readonly ids: readonly string[] }
    | { readonly ok: false; readonly reason: string } {
    if (!body || !Array.isArray((body as { ids?: unknown }).ids)) {
      return { ok: false, reason: "ids must be an array" }
    }
    const ids = (body as { ids: readonly unknown[] }).ids
    if (ids.length === 0) {
      return { ok: false, reason: "ids must not be empty" }
    }
    if (ids.length > 50) {
      return { ok: false, reason: "batch too large (max 50)" }
    }
    if (!ids.every((x) => typeof x === "string" && x.trim().length > 0)) {
      return { ok: false, reason: "ids must be non-empty strings" }
    }
    return { ok: true, ids: ids as readonly string[] }
  }

  async function handleBatch(args: {
    readonly store: DurableMemoryStore
    readonly subject: string
    readonly ids: readonly string[]
    readonly transform: (record: DurableMemoryRecord, nowMs: number) => DurableMemoryRecord
  }): Promise<{
    readonly succeeded: readonly string[]
    readonly failed: readonly { readonly id: string; readonly reason: string }[]
  }> {
    const nowMs = Date.now()
    const dedupedIds = Array.from(
      new Set(args.ids.map((s) => s.trim()).filter((s) => s.length > 0)),
    )
    const succeeded: string[] = []
    const failed: { id: string; reason: string }[] = []
    for (const id of dedupedIds) {
      try {
        const record = await args.store.get(id)
        if (!record) {
          failed.push({ id, reason: "not found" })
          continue
        }
        if (record.subject !== args.subject) {
          failed.push({ id, reason: "subject mismatch" })
          continue
        }
        if (record.status === "confirmed") {
          failed.push({ id, reason: "already confirmed" })
          continue
        }
        if (record.status === "rejected") {
          failed.push({ id, reason: "already rejected" })
          continue
        }
        if (record.status === "expired") {
          failed.push({ id, reason: "already expired" })
          continue
        }
        const updated = await args.store.update(args.transform(record, nowMs))
        succeeded.push(updated.id)
      } catch (err) {
        // Malformed UUIDs (e.g. "missing-id") surface as PG syntax errors on
        // the underlying get query; treat those uniformly as "not found" so
        // callers never see driver-level error text in the failed list. This
        // special-case is checked FIRST so the generic catch path is reserved
        // for truly unexpected programming errors.
        const message = err instanceof Error ? err.message : "unknown error"
        if (message.includes("invalid input syntax for type uuid")) {
          failed.push({ id, reason: "not found" })
          continue
        }
        // Truly unexpected error — surface the raw message in the per-id
        // failed list (callers can act on it) without polluting stdout.
        failed.push({ id, reason: message })
      }
    }
    return { succeeded, failed }
  }

  // G2 dedup — module-scoped env-driven config (D41 T3 dedup-config).
  // Defined once at route init so we don't re-read env on every request.
  // Shared checker is also used by the document promote-memory route.
  const checkDedup = makeDedupChecker()

  // G4 auto-promote — module-scoped env-driven config (D42 T6 auto-promote-config).
  // Used by /v1/owner/memories/:memoryId/rollback-auto-promote for rollbackWindowMs.
  const autoPromoteCfg = parseAutoPromoteConfig(process.env)

  app.post("/v1/owner/memories/confirm-batch", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.durableMemoryStore
    if (!store) return c.json({ ok: false, reason: "durable memory store unavailable" }, 503)
    const body = (await c.req.json().catch(() => null)) ?? null
    const parsed = parseBatchIds(body)
    if (!parsed.ok) {
      return c.json({ ok: false, reason: parsed.reason }, 400)
    }
    const subject = (c.req.query("subject") ?? "owner").trim() || "owner"
    const result = await handleBatch({
      store,
      subject,
      ids: parsed.ids,
      transform: (record, nowMs) => confirmDurableMemory(record, nowMs),
    })
    return c.json({ confirmed: result.succeeded, failed: result.failed })
  })

  app.post("/v1/owner/memories/reject-batch", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const store = wiring.durableMemoryStore
    if (!store) return c.json({ ok: false, reason: "durable memory store unavailable" }, 503)
    const body = (await c.req.json().catch(() => null)) ?? null
    const parsed = parseBatchIds(body)
    if (!parsed.ok) {
      return c.json({ ok: false, reason: parsed.reason }, 400)
    }
    const subject = (c.req.query("subject") ?? "owner").trim() || "owner"
    const result = await handleBatch({
      store,
      subject,
      ids: parsed.ids,
      transform: (record, nowMs) => rejectDurableMemory(record, nowMs),
    })
    return c.json({ rejected: result.succeeded, failed: result.failed })
  })
}

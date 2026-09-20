import type { Hono } from "hono"
import {
  confirmDurableMemory,
  createDurableMemoryRecord,
  rejectDurableMemory,
  type DurableMemoryRecord,
  type DurableMemoryStatus,
} from "@butler/domain/knowledge/durable-memory.js"
import type { DurableMemoryStore } from "@butler/persistence"
import { parseAutoPromoteConfig } from "../auto-promote-config.js"
import type { Wiring } from "../wiring.js"
import { ownerAuthorized } from "../owner-auth.js"
import { makeDedupChecker } from "./memory-dedup.js"
import { handleRollbackAutoPromote } from "./memories-rollback.js"
import { isAllowedSubject, safeOwnerErrorString, unauthorizedForOwner } from "../owner-jargon.js"

/**
 * Owner control-surface routes for durable memories, including batch
 * confirm/reject helpers and G2 dedup / G4 auto-promote rollback guards.
 * Split from owner-routes.ts (file-size gate) — behavior unchanged.
 */
export function registerMemoriesRoutes(app: Hono, wiring: Wiring): void {
  app.get("/v1/owner/memories", async (c) => {
    if (!ownerAuthorized(c)) return unauthorizedForOwner(c)
    const store = wiring.durableMemoryStore
    if (!store) return c.json({ ok: false, reason: "持久化记忆库暂不可用" }, 503)
    const subject = (c.req.query("subject") ?? "owner").trim() || "owner"
    const statusRaw = (c.req.query("status") ?? "").trim()
    const status: DurableMemoryStatus | undefined =
      statusRaw === "candidate" || statusRaw === "confirmed" || statusRaw === "rejected" || statusRaw === "expired"
        ? statusRaw
        : undefined
    if (statusRaw && !status) {
      return c.json({ ok: false, reason: "状态参数无效（必须是 candidate/confirmed/rejected/expired）" }, 400)
    }
    const limitRaw = c.req.query("limit")
    const limit = limitRaw ? Number.parseInt(limitRaw, 10) : 20
    if (!Number.isFinite(limit) || limit < 1 || limit > 100) {
      return c.json({ ok: false, reason: "limit 参数超出范围（1-100，默认 20）" }, 400)
    }
    const offsetRaw = c.req.query("offset")
    const offset = offsetRaw ? Number.parseInt(offsetRaw, 10) : 0
    if (!Number.isFinite(offset) || offset < 0) {
      return c.json({ ok: false, reason: "offset 参数无效（>=0，默认 0）" }, 400)
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
    if (!ownerAuthorized(c)) return unauthorizedForOwner(c)
    const store = wiring.durableMemoryStore
    if (!store) return c.json({ ok: false, reason: "持久化记忆库暂不可用" }, 503)
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
    if (!created.ok) return c.json({ ok: false, reason: safeOwnerErrorString(created.reason) }, 400)
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
    // D62 T1 (audit #1 F-12): close §13 audit completeness gap for the
    // create path. D58 T4 closed confirm/reject/delete/rollback but
    // missed create. Best-effort: a failed audit write must not block
    // the owner-facing response (the memory is already saved).
    try {
      await wiring.runtimeStore.appendAuditEvent({
        auditId: crypto.randomUUID(),
        runId: null,
        conversationId: null,
        // D66 T1b-apps-api: thread request-scoped correlation. Owner
        // direct API call; no inbound run — pass null.
        correlationId: null,
        action: "memory.created",
        // D73 T4 (audit #19 SO-011): owner-direct actor sentinel — distinguishes from wechat-inbound 'fatigue-agent' in audit_events.
        actor: 'owner-direct',
        // D74 T1 (audit #20 SO-007): subject allowlist — audit emit must
        // reject attacker-controllable subjects at the boundary. Defaults
        // to "owner" rather than echoing body.subject if disallowed.
        subject: body.subject && isAllowedSubject(body.subject) ? body.subject : "owner",
        detail: {
          memoryId: saved.id,
          sourceKind: created.value.sourceKind,
          status: saved.status,
        },
        createdAt: new Date(),
      })
    } catch (err) {
      // eslint-disable-next-line no-console -- operator log when no logger injected
      console.error("[memories] appendAuditEvent (memory.created) failed:", err)
    }
    return c.json({ ok: true, item: saved })
  })

  app.post("/v1/owner/memories/:memoryId/confirm", async (c) => {
    if (!ownerAuthorized(c)) return unauthorizedForOwner(c)
    const store = wiring.durableMemoryStore
    if (!store) return c.json({ ok: false, reason: "持久化记忆库暂不可用" }, 503)
    const memoryId = c.req.param("memoryId")
    const existing = await store.get(memoryId)
    if (!existing) return c.json({ ok: false, reason: "未找到对应记录" }, 404)
    if (existing.status === "confirmed") {
      return c.json({ ok: false, reason: "已是已确认状态" }, 409)
    }
    if (existing.status === "expired") {
      return c.json({ ok: false, reason: "已是已过期状态" }, 409)
    }
    const updated = await store.update(confirmDurableMemory(existing, Date.now()))
    // D58 T4 (audit #3 F-03): §13 audit completeness — owner state
    // transitions must leave an audit_event row. Mirror mcp.ts revoke-grants.
    await wiring.runtimeStore.appendAuditEvent({
      auditId: crypto.randomUUID(),
      runId: null,
      conversationId: null,
      // D66 T1b-apps-api: thread request-scoped correlation. Owner
      // direct API call; no inbound run — pass null.
      correlationId: null,
      action: "memory.confirmed",
      // D73 T4 (audit #19 SO-011): owner-direct actor sentinel — distinguishes from wechat-inbound 'fatigue-agent' in audit_events.
      actor: 'owner-direct',
      subject: "owner",
      detail: { memoryId },
      createdAt: new Date(),
    })
    return c.json({ ok: true, item: updated })
  })

  app.post("/v1/owner/memories/:memoryId/reject", async (c) => {
    if (!ownerAuthorized(c)) return unauthorizedForOwner(c)
    const store = wiring.durableMemoryStore
    if (!store) return c.json({ ok: false, reason: "持久化记忆库暂不可用" }, 503)
    const memoryId = c.req.param("memoryId")
    const existing = await store.get(memoryId)
    if (!existing) return c.json({ ok: false, reason: "未找到对应记录" }, 404)
    if (existing.status === "rejected") {
      return c.json({ ok: false, reason: "已是已拒绝状态" }, 409)
    }
    if (existing.status === "expired") {
      return c.json({ ok: false, reason: "已是已过期状态" }, 409)
    }
    const updated = await store.update(rejectDurableMemory(existing, Date.now()))
    // D58 T4 (audit #3 F-03): §13 audit completeness.
    await wiring.runtimeStore.appendAuditEvent({
      auditId: crypto.randomUUID(),
      runId: null,
      conversationId: null,
      // D66 T1b-apps-api: thread request-scoped correlation. Owner
      // direct API call; no inbound run — pass null.
      correlationId: null,
      action: "memory.rejected",
      // D73 T4 (audit #19 SO-011): owner-direct actor sentinel — distinguishes from wechat-inbound 'fatigue-agent' in audit_events.
      actor: 'owner-direct',
      subject: "owner",
      detail: { memoryId },
      createdAt: new Date(),
    })
    return c.json({ ok: true, item: updated })
  })

  // G4: owner rollback for sweeper-auto-promoted records (§12).
  // Extracted to ./memories-rollback.ts (D65 T2a) — body unchanged.
  app.post("/v1/owner/memories/:memoryId/rollback-auto-promote", async (c) =>
    handleRollbackAutoPromote(c, wiring, autoPromoteCfg.rollbackWindowMs),
  )

  app.delete("/v1/owner/memories/:memoryId", async (c) => {
    if (!ownerAuthorized(c)) return unauthorizedForOwner(c)
    const store = wiring.durableMemoryStore
    if (!store) return c.json({ ok: false, reason: "持久化记忆库暂不可用" }, 503)
    const memoryId = c.req.param("memoryId")
    const ok = await store.delete(memoryId)
    if (!ok) return c.json({ ok: false, reason: "未找到对应记录" }, 404)
    // D58 T4 (audit #3 F-03): §13 audit completeness.
    await wiring.runtimeStore.appendAuditEvent({
      auditId: crypto.randomUUID(),
      runId: null,
      conversationId: null,
      // D66 T1b-apps-api: thread request-scoped correlation. Owner
      // direct API call; no inbound run — pass null.
      correlationId: null,
      action: "memory.deleted",
      // D73 T4 (audit #19 SO-011): owner-direct actor sentinel — distinguishes from wechat-inbound 'fatigue-agent' in audit_events.
      actor: 'owner-direct',
      subject: "owner",
      detail: { memoryId },
      createdAt: new Date(),
    })
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
          failed.push({ id, reason: "未找到对应记录" })
          continue
        }
        if (record.subject !== args.subject) {
          failed.push({ id, reason: "主体不匹配" })
          continue
        }
        if (record.status === "confirmed") {
          failed.push({ id, reason: "已是已确认状态" })
          continue
        }
        if (record.status === "rejected") {
          failed.push({ id, reason: "已是已拒绝状态" })
          continue
        }
        if (record.status === "expired") {
          failed.push({ id, reason: "已是已过期状态" })
          continue
        }
        const updated = await args.store.update(args.transform(record, nowMs))
        succeeded.push(updated.id)
      } catch (err) {
        // D74 T1 (audit #20 SO-003): route err.message through
        // safeOwnerErrorString so PG error vocabulary
        // ('invalid input syntax for type uuid: "..."', 'duplicate key
        // value...') translates to Chinese; unknown errors get the
        // generic "操作失败，请稍后重试" fallback. Previously leaked raw
        // PG text to owner HTTP response.
        const message = err instanceof Error ? err.message : "unknown error"
        failed.push({ id, reason: safeOwnerErrorString(message) })
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
    if (!ownerAuthorized(c)) return unauthorizedForOwner(c)
    const store = wiring.durableMemoryStore
    if (!store) return c.json({ ok: false, reason: "持久化记忆库暂不可用" }, 503)
    const body = (await c.req.json().catch(() => null)) ?? null
    const parsed = parseBatchIds(body)
    if (!parsed.ok) {
      return c.json({ ok: false, reason: safeOwnerErrorString(parsed.reason) }, 400)
    }
    const subject = (c.req.query("subject") ?? "owner").trim() || "owner"
    const result = await handleBatch({
      store,
      subject,
      ids: parsed.ids,
      transform: (record, nowMs) => confirmDurableMemory(record, nowMs),
    })
    // D58 T4 (audit #3 F-03): one audit_event per succeeded id.
    const now = new Date()
    await Promise.all(
      result.succeeded.map((memoryId) =>
        wiring.runtimeStore.appendAuditEvent({
          auditId: crypto.randomUUID(),
          runId: null,
          conversationId: null,
          // D66 T1b-apps-api: thread request-scoped correlation. Owner
          // direct API call; no inbound run — pass null.
          correlationId: null,
          action: "memory.confirmed",
          // D73 T4 (audit #19 SO-011): owner-direct actor sentinel — distinguishes from wechat-inbound 'fatigue-agent' in audit_events.
          actor: 'owner-direct',
          subject,
          detail: { memoryId, batch: true },
          createdAt: now,
        }),
      ),
    )
    return c.json({ confirmed: result.succeeded, failed: result.failed })
  })

  app.post("/v1/owner/memories/reject-batch", async (c) => {
    if (!ownerAuthorized(c)) return unauthorizedForOwner(c)
    const store = wiring.durableMemoryStore
    if (!store) return c.json({ ok: false, reason: "持久化记忆库暂不可用" }, 503)
    const body = (await c.req.json().catch(() => null)) ?? null
    const parsed = parseBatchIds(body)
    if (!parsed.ok) {
      return c.json({ ok: false, reason: safeOwnerErrorString(parsed.reason) }, 400)
    }
    const subject = (c.req.query("subject") ?? "owner").trim() || "owner"
    const result = await handleBatch({
      store,
      subject,
      ids: parsed.ids,
      transform: (record, nowMs) => rejectDurableMemory(record, nowMs),
    })
    // D58 T4 (audit #3 F-03): one audit_event per succeeded id.
    const now = new Date()
    await Promise.all(
      result.succeeded.map((memoryId) =>
        wiring.runtimeStore.appendAuditEvent({
          auditId: crypto.randomUUID(),
          runId: null,
          conversationId: null,
          // D66 T1b-apps-api: thread request-scoped correlation. Owner
          // direct API call; no inbound run — pass null.
          correlationId: null,
          action: "memory.rejected",
          // D73 T4 (audit #19 SO-011): owner-direct actor sentinel — distinguishes from wechat-inbound 'fatigue-agent' in audit_events.
          actor: 'owner-direct',
          subject,
          detail: { memoryId, batch: true },
          createdAt: now,
        }),
      ),
    )
    return c.json({ rejected: result.succeeded, failed: result.failed })
  })
}

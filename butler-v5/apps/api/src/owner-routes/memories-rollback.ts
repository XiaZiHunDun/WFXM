/**
 * D65 T2a — Extract `rollback-auto-promote` handler from memories.ts.
 *
 * G4 owner-driven undo path within the 7d post-promote rollback window.
 * Pure domain validation + audit log on every response (200/404/409).
 *
 * Concurrent modification between validate and UPDATE is handled explicitly:
 * store.rollbackAutoPromoted returns null when WHERE status='confirmed'
 * AND promoted_by='sweeper' no longer matches (e.g. another rollback raced).
 *
 * Behavior unchanged from original inline handler.
 */
import type { Context } from "hono"
import { rollbackAutoPromotedCandidate } from "@butler/domain/knowledge/auto-promote.js"
import type { Wiring } from "../wiring.js"
import { ownerAuthorized } from "../owner-auth.js"

export async function handleRollbackAutoPromote(
  c: Context,
  wiring: Wiring,
  rollbackWindowMs: number,
): Promise<Response> {
  if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
  const store = wiring.durableMemoryStore
  if (!store) return c.json({ ok: false, reason: "durable memory store unavailable" }, 503)
  // Route param is guaranteed by the registered route path
  // `/v1/owner/memories/:memoryId/rollback-auto-promote`.
  const memoryId = c.req.param("memoryId") ?? ""
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
    rollbackWindowMs,
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
            ? new Date(memory.promotedAt + rollbackWindowMs).toISOString()
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
  // D58 T4 (audit #3 F-02): rollback mutated durable state with only
  // stderr logging before. Now mirror mcp.ts revoke-grants and write
  // an audit_event row so owner queries on audit_events find rollbacks.
  await wiring.runtimeStore.appendAuditEvent({
    auditId: crypto.randomUUID(),
    runId: null,
    conversationId: null,
    action: "memory.rollback",
    subject: "owner",
    detail: { memoryId, reason: body.reason ?? null },
    createdAt: now,
  })
  return c.json({ memory: updated })
}

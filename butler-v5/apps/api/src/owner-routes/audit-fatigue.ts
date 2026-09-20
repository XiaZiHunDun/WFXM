import type { Hono } from "hono"
import type { Wiring } from "../wiring.js"
import { ownerAuthorized } from "../owner-auth.js"
import { auditFatigueReader } from "../lib/fatigue/audit-reader.js"
import {
  CrossActorReplayError,
  listFatigueSequences,
  replayFatigueSequence,
  type UndoFn,
} from "../lib/fatigue/replay.js"
import { undoLastWrite } from "../workspace-tools.js"
import { unauthorizedForOwner } from "../owner-jargon.js"

/**
 * D69 T1 — owner audit fatigue replay API.
 *
 * Exposes two endpoints for the owner control surface:
 *   GET  /v1/owner/audit/fatigue?window_seconds=N
 *     — list sequences of >=3 owner actions within window_seconds, grouped
 *       by 10s gaps. Returns `degraded: true` when the audit log read fails.
 *   POST /v1/owner/audit/fatigue/replay
 *     — replay (or mark irreversible) a list of audit event_ids. Cross-actor
 *       events are rejected with 403.
 *
 * Reader acquisition is now `auditFatigueReader(wiring.runtimeStore)`,
 * shared with `wechat-inbound-butler.ts` via
 * `apps/api/src/lib/fatigue/audit-reader.ts` (D69 T1 consolidation; closes
 * the pre-scoped D68 follow-ups #1 + #2). Previously this route read the
 * subagent JSONL log via `readRecentSubagentAudit` — that source only
 * observed subagent delegations, so the owner control surface missed
 * fatigue decisions emitted by other entry points. The runtime
 * `audit_events` table is now the canonical source for both readers.
 *
 * ownerId / cross-actor: this control surface is loopback-only (no bearer
 * token). The canonical owner actor string is "owner" — matching what
 * `auditFatigueReader` emits. When proper owner auth with bearer is
 * added, ownerId will come from the authenticated session and the
 * cross-actor check becomes a real identity boundary instead of a
 * sentinel match.
 *
 * D70 T1 (audit #11 CQ-010): undo dispatcher is now required and actually
 * invokes the undo machinery. Previously the function returned
 * `replayed: [eventId]` for reversible events without doing anything
 * — silent no-op bug. The dispatcher maps (toolName, eventId, actor)
 * onto the right undo (write_file/edit_file → undoLastWrite via path +
 * workspaceRoot in audit_event.detail; everything else → returns
 * failure with an owner-jargon reason). Routes the outcome into
 * `replayed` (ok) or `failed` (not ok).
 */

function currentOwnerActor(): string {
  // D73 T4 (audit #19 SO-011): thread 'owner-direct' to match the sentinel
  // emitted by every owner-direct appendAuditEvent call site. Previously
  // returned 'owner' which matched the schema default — collapsed with
  // wechat-inbound fatigue emits and made the cross-actor replay check
  // (replay.ts:122) functionally inert.
  return "owner-direct"
}

interface ReplayBody {
  readonly sequence_event_ids: readonly string[]
}

const MAX_REPLAY_BATCH = 1000

function isReplayBody(value: unknown): value is ReplayBody {
  if (!value || typeof value !== "object") return false
  const v = value as { sequence_event_ids?: unknown }
  if (!Array.isArray(v.sequence_event_ids)) return false
  if (v.sequence_event_ids.length === 0 || v.sequence_event_ids.length > MAX_REPLAY_BATCH) return false
  return v.sequence_event_ids.every((id) => typeof id === "string" && id.length > 0)
}

/**
 * D70 T1 (CQ-010): real undo dispatcher. Looks up the audit event detail
 * for `write_file` / `edit_file` to extract path + workspaceRoot, then
 * calls `undoLastWrite`. Returns failure with owner-jargon reason when
 * the audit event is missing the path detail (D71+ infrastructure
 * work: thread path/workspaceRoot into appendAuditEvent at every
 * tool-execution chokepoint — currently only fatigue decisions are
 * audited, not the actual write).
 */
async function ownerAuditUndo(
  wiring: Wiring,
  toolName: string,
  eventId: string,
  actor: string,
): Promise<{ readonly ok: true } | { readonly ok: false; readonly reason: string }> {
  let detail: Readonly<Record<string, unknown>> = {}
  try {
    const events = await wiring.runtimeStore.listRecentAuditEvents({
      actor,
      windowMs: 24 * 60 * 60 * 1000,
      limit: 1000,
    })
    const event = events.find(e => e.auditId === eventId)
    detail = event?.detail ?? {}
  } catch {
    // fall through with empty detail
  }

  if (toolName === "write_file" || toolName === "edit_file") {
    const path = (detail as { path?: unknown }).path
    const workspaceRoot = (detail as { workspaceRoot?: unknown }).workspaceRoot
    if (typeof path !== "string" || typeof workspaceRoot !== "string") {
      return {
        ok: false,
        reason: `缺少操作目标信息（文件路径），无法撤销 ${toolName}`,
      }
    }
    const result = undoLastWrite(workspaceRoot, path)
    if (result === undefined) {
      return { ok: false, reason: `撤销栈中找不到 ${path} 的写入记录` }
    }
    return { ok: true }
  }
  return { ok: false, reason: `暂不支持撤销 ${toolName}` }
}

export function registerAuditFatigueRoutes(app: Hono, wiring: Wiring): void {
  const reader = auditFatigueReader(wiring.runtimeStore, { columnActor: true })

  app.get("/v1/owner/audit/fatigue", async (c) => {
    if (!ownerAuthorized(c)) return unauthorizedForOwner(c)
    const windowRaw = Number(c.req.query("window_seconds") ?? "60")
    const windowSeconds = Number.isFinite(windowRaw) && windowRaw > 0 ? Math.floor(windowRaw) : 60
    const result = await listFatigueSequences(reader, currentOwnerActor(), windowSeconds)
    return c.json(result)
  })

  app.post("/v1/owner/audit/fatigue/replay", async (c) => {
    if (!ownerAuthorized(c)) return unauthorizedForOwner(c)
    const raw: unknown = await c.req.json().catch(() => null)
    if (!isReplayBody(raw)) {
      return c.json({ error: `请求体格式错误：需要 { sequence_event_ids: 字符串数组 }（1-${MAX_REPLAY_BATCH} 个）` }, 400)
    }
    // D70 T1: capture ownerActor once and pass it to replayFatigueSequence
    // alongside the undo dispatcher. The dispatcher closes the silent
    // no-op bug (CQ-010) by actually invoking undo machinery for
    // reversible events and routing failures into result.failed.
    const ownerActor = currentOwnerActor()
    const undo: UndoFn = (toolName, eventId, actor) =>
      ownerAuditUndo(wiring, toolName, eventId, actor)
    try {
      const result = await replayFatigueSequence(reader, raw.sequence_event_ids, ownerActor, undo)
      // D69 T5 (audit #10 SO-16): §13 audit completeness — every other
      // owner-mutating endpoint (rollback, confirm, reject, mcp.revoke-grants)
      // emits an audit_event. POST /v1/owner/audit/fatigue/replay previously
      // did not. Mirror memories-rollback.ts:120 pattern.
      await wiring.runtimeStore.appendAuditEvent({
        auditId: crypto.randomUUID(),
        runId: null,
        conversationId: null,
        correlationId: null,
        action: "owner.replay",
        // D73 T4 (audit #19 SO-011): owner-direct actor sentinel — distinguishes from wechat-inbound 'fatigue-agent' in audit_events.
        actor: 'owner-direct',
        subject: ownerActor,
        detail: {
          sequence_event_ids: raw.sequence_event_ids.slice(0, 50),
          replayed: result.replayed.length,
          irreversible: result.irreversible.length,
          failed: result.failed.length,
        },
        createdAt: new Date(),
      })
      return c.json(result)
    } catch (err) {
      // D69 T3 (audit #10 SO-13/SO-19): typed catch via instanceof instead
      // of err.message.includes("cross-actor") string match. The error
      // message is owner-jargon Chinese ("拒绝跨账号操作") rather than
      // English internal jargon.
      if (err instanceof CrossActorReplayError) {
        return c.json({ error: "拒绝跨账号操作：该操作不属于你的账号" }, 403)
      }
      throw err
    }
  })
}
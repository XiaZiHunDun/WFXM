import type { Hono } from "hono"
import type { Wiring } from "../wiring.js"
import { ownerAuthorized } from "../owner-auth.js"
import { readRecentSubagentAudit } from "../audit-log.js"
import {
  listFatigueSequences,
  replayFatigueSequence,
} from "../lib/fatigue/replay.js"
import type { AuditEventSummary, AuditLogReader } from "../lib/fatigue/signal.js"

/**
 * D64 T4: owner audit fatigue replay API.
 *
 * Exposes two endpoints for the owner control surface:
 *   GET  /v1/owner/audit/fatigue?window_seconds=N
 *     — list sequences of >=3 owner actions within window_seconds, grouped
 *       by 10s gaps. Returns `degraded: true` when the audit log read fails.
 *   POST /v1/owner/audit/fatigue/replay
 *     — replay (or mark irreversible) a list of audit event_ids. Cross-actor
 *       events are rejected with 403.
 *
 * Reader acquisition mirrors wechat-inbound-butler.ts:subagentAuditAsFatigueReader
 * (D64 T3). The two adapters read the same JSONL source via
 * readRecentSubagentAudit; we inline the conversion here rather than
 * importing the helper from wechat-inbound-butler.ts (which would couple
 * route modules to the butler loop). If a third caller lands in D65+,
 * extract to apps/api/src/lib/fatigue/audit-reader.ts (YAGNI for now).
 *
 * GAP (D64 follow-up): once the runtime audit_events table gains a dedicated
 * read method (listRecentAuditEvents), replace readRecentSubagentAudit here
 * with a query over audit_events so owner audit fatigue observes decisions
 * across all entry points, not just subagent delegations.
 *
 * ownerId / cross-actor: this control surface is loopback-only (no bearer
 * token). The canonical owner actor string is "owner" — matching what
 * appendAudit() emits via ownerSubject for normal owner-initiated runs.
 * When proper owner auth with bearer is added, ownerId will come from the
 * authenticated session and the cross-actor check becomes a real identity
 * boundary instead of a sentinel match.
 */

const OWNER_ACTOR = "owner"

function ownerAuditReader(): AuditLogReader {
  return {
    readRecent: async (windowMs: number): Promise<readonly AuditEventSummary[]> => {
      const limit = Math.min(50, Math.max(1, Math.ceil(windowMs / 1000)))
      const rows = readRecentSubagentAudit(limit, process.env)
      return rows
        .filter((r) => typeof r.toolName === "string" && r.toolName.length > 0)
        .map((r) => ({
          event_id: `${r.parentConversationId}:${r.ts}`,
          tool_name: r.toolName as string,
          actor: r.ownerSubject ?? r.role,
          ts: Date.parse(r.ts) || 0,
          decision: "allow" as const,
        }))
    },
  }
}

interface ReplayBody {
  readonly sequence_event_ids: readonly string[]
}

function isReplayBody(value: unknown): value is ReplayBody {
  if (!value || typeof value !== "object") return false
  const v = value as { sequence_event_ids?: unknown }
  if (!Array.isArray(v.sequence_event_ids)) return false
  return v.sequence_event_ids.every((id) => typeof id === "string" && id.length > 0)
}

export function registerAuditFatigueRoutes(app: Hono, _wiring: Wiring): void {
  app.get("/v1/owner/audit/fatigue", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const windowRaw = Number(c.req.query("window_seconds") ?? "60")
    const windowSeconds = Number.isFinite(windowRaw) && windowRaw > 0 ? Math.floor(windowRaw) : 60
    const reader = ownerAuditReader()
    const result = await listFatigueSequences(reader, OWNER_ACTOR, windowSeconds)
    return c.json(result)
  })

  app.post("/v1/owner/audit/fatigue/replay", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const raw: unknown = await c.req.json().catch(() => null)
    if (!isReplayBody(raw)) {
      return c.json({ error: "invalid body: expected { sequence_event_ids: string[] }" }, 400)
    }
    const reader = ownerAuditReader()
    try {
      const result = await replayFatigueSequence(reader, raw.sequence_event_ids, OWNER_ACTOR)
      return c.json(result)
    } catch (err) {
      if (err instanceof Error && err.message.includes("cross-actor")) {
        return c.json({ error: "cross-actor replay rejected" }, 403)
      }
      throw err
    }
  })
}
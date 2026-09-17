import type { Hono } from "hono"
import type { Wiring } from "../wiring.js"
import { ownerAuthorized } from "../owner-auth.js"
import { auditFatigueReader } from "../lib/fatigue/audit-reader.js"
import {
  CrossActorReplayError,
  listFatigueSequences,
  replayFatigueSequence,
} from "../lib/fatigue/replay.js"

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
 */

function currentOwnerActor(): string {
  return "owner"
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

export function registerAuditFatigueRoutes(app: Hono, wiring: Wiring): void {
  const reader = auditFatigueReader(wiring.runtimeStore)

  app.get("/v1/owner/audit/fatigue", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const windowRaw = Number(c.req.query("window_seconds") ?? "60")
    const windowSeconds = Number.isFinite(windowRaw) && windowRaw > 0 ? Math.floor(windowRaw) : 60
    const result = await listFatigueSequences(reader, currentOwnerActor(), windowSeconds)
    return c.json(result)
  })

  app.post("/v1/owner/audit/fatigue/replay", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const raw: unknown = await c.req.json().catch(() => null)
    if (!isReplayBody(raw)) {
      return c.json({ error: `invalid body: expected { sequence_event_ids: string[] } (1-${MAX_REPLAY_BATCH} ids)` }, 400)
    }
    try {
      const result = await replayFatigueSequence(reader, raw.sequence_event_ids, currentOwnerActor())
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
        subject: currentOwnerActor(),
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
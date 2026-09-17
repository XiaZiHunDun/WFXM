import { DEFAULT_COUNT_THRESHOLD } from "./signal"
import type { AuditLogReader, AuditEventSummary } from "./signal"

export interface FatigueSequence {
  readonly start_ts: number
  readonly end_ts: number
  readonly count: number
  readonly event_ids: readonly string[]
}

export interface ListFatigueSequencesResult {
  readonly sequences: readonly FatigueSequence[]
  readonly degraded?: true
}

export interface ReplayResult {
  readonly replayed: readonly string[]
  readonly irreversible: readonly string[]
  readonly failed: readonly { event_id: string; reason: string }[]
}

/**
 * D70 T1 (audit #11 CQ-010) — undo dispatcher for replay.
 *
 * Previously `replayFatigueSequence` returned `replayed: [eventId]` for
 * reversible events without actually invoking undo. The owner-facing
 * POST /v1/owner/audit/fatigue/replay endpoint returned success while
 * doing nothing — silent no-op bug. Callers now MUST pass an `undo`
 * dispatcher; the function dispatches to it for every reversible event
 * and routes the outcome into `replayed` (ok) or `failed` (not ok).
 */
export type UndoFn = (
  toolName: string,
  eventId: string,
  actor: string,
) => Promise<{ readonly ok: true } | { readonly ok: false; readonly reason: string }>

const SEQUENCE_GAP_MS = 10_000 // 10s gap = new sequence
const IRREVERSIBLE_TOOLS = ['send_*', 'broadcast_*', 'external_write', 'run_command']
const REPLAY_WINDOW_HOURS = 24

// Precompile irreversible patterns once (regex metachars + glob * → .*)
// Matches checklist.ts:globToRegex so sibling files share one escape strategy.
const IRREVERSIBLE_PATTERNS = IRREVERSIBLE_TOOLS.map(pattern => {
  const escaped = pattern.replace(/[.+?^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*')
  return new RegExp('^' + escaped + '$')
})

function isIrreversible(toolName: string): boolean {
  return IRREVERSIBLE_PATTERNS.some(regex => regex.test(toolName))
}

function groupIntoSequences(events: readonly AuditEventSummary[]): readonly FatigueSequence[] {
  if (events.length === 0) return []
  const sorted = [...events].sort((a, b) => a.ts - b.ts)
  const sequences: FatigueSequence[] = []
  let currentGroup: AuditEventSummary[] = [sorted[0] as AuditEventSummary]

  for (let i = 1; i < sorted.length; i++) {
    const current = sorted[i] as AuditEventSummary
    const previous = sorted[i - 1] as AuditEventSummary
    if (current.ts - previous.ts > SEQUENCE_GAP_MS) {
      pushIfSequence(sequences, currentGroup)
      currentGroup = [current]
    } else {
      currentGroup.push(current)
    }
  }
  // tail group
  pushIfSequence(sequences, currentGroup)
  // sort DESC by start_ts
  return sequences.sort((a, b) => b.start_ts - a.start_ts)
}

function pushIfSequence(
  sequences: FatigueSequence[],
  group: readonly AuditEventSummary[],
): void {
  if (group.length < DEFAULT_COUNT_THRESHOLD) return
  const first = group[0] as AuditEventSummary
  const last = group[group.length - 1] as AuditEventSummary
  sequences.push({
    start_ts: first.ts,
    end_ts: last.ts,
    count: group.length,
    event_ids: group.map(e => e.event_id),
  })
}

export async function listFatigueSequences(
  reader: AuditLogReader,
  ownerActor: string,
  windowSeconds: number,
): Promise<ListFatigueSequencesResult> {
  try {
    const events = await reader.readRecent(windowSeconds * 1000)
    const ownerEvents = events.filter(e => e.actor === ownerActor)
    return { sequences: groupIntoSequences(ownerEvents) }
  } catch {
    return { sequences: [], degraded: true }
  }
}

export async function replayFatigueSequence(
  reader: AuditLogReader,
  sequenceEventIds: readonly string[],
  ownerActor: string,
  undo: UndoFn,
): Promise<ReplayResult> {
  const events = await reader.readRecent(REPLAY_WINDOW_HOURS * 60 * 60 * 1000)
  const byId = new Map(events.map(e => [e.event_id, e]))
  const replayed: string[] = []
  const irreversible: string[] = []
  const failed: { event_id: string; reason: string }[] = []

  for (const eventId of sequenceEventIds) {
    const event = byId.get(eventId)
    if (!event) {
      failed.push({ event_id: eventId, reason: 'event not found in 24h window' })
      continue
    }
    if (event.actor !== ownerActor) {
      throw new CrossActorReplayError(eventId, ownerActor, event.actor)
    }
    if (isIrreversible(event.tool_name)) {
      irreversible.push(eventId)
      continue
    }
    // D70 T1: actually invoke undo. The dispatcher is the only place that
    // knows how to map a (toolName, eventId, actor) tuple to the right
    // undo machinery (undoLastWrite / undoChain / etc). On success →
    // replayed; on failure → failed with the dispatcher's reason.
    const result = await undo(event.tool_name, eventId, event.actor)
    if (result.ok) {
      replayed.push(eventId)
    } else {
      failed.push({ event_id: eventId, reason: result.reason })
    }
  }

  return { replayed, irreversible, failed }
}

/**
 * D69 T3 (audit #10 SO-13): typed error for cross-actor replay rejection.
 * Previously the owner-routes audit-fatigue handler caught with
 * `err.message.includes("cross-actor")` — brittle string match that
 * silently degraded a 403 into a 500 if the throw site renamed the
 * message. The error message is kept (with "cross-actor" / "not owner"
 * tokens) so the existing replay-api.test.ts R4 regex
 * (/cross-actor|not owner/i) still passes; callers should prefer
 * `instanceof CrossActorReplayError`.
 */
export class CrossActorReplayError extends Error {
  override readonly name = "CrossActorReplayError" as const
  constructor(
    readonly eventId: string,
    readonly expectedActor: string,
    readonly actualActor: string,
  ) {
    super(
      `cross-actor replay rejected: event ${eventId} not owned by ${expectedActor} (actual: ${actualActor})`,
    )
  }
}
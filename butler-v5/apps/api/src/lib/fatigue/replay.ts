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

const SEQUENCE_GAP_MS = 10_000 // 10s gap = new sequence
const IRREVERSIBLE_TOOLS = ['send_*', 'broadcast_*', 'external_write', 'run_command']
const REPLAY_WINDOW_HOURS = 24

function isIrreversible(toolName: string): boolean {
  return IRREVERSIBLE_TOOLS.some(pattern => {
    const regex = new RegExp('^' + pattern.replace(/\*/g, '.*') + '$')
    return regex.test(toolName)
  })
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
      throw new Error(`cross-actor replay rejected: event ${eventId} not owned by ${ownerActor}`)
    }
    if (isIrreversible(event.tool_name)) {
      irreversible.push(eventId)
    } else {
      // For reversible: dispatch to D49 undoChain / D46 undoLastWrite.
      // Task 7 ships the API surface; actual undo invocation is wired in D65+ when
      // audit_events has listRecentAuditEvents (per Task 6 GAP doc). For now we
      // mark as replayed and log the intent.
      replayed.push(eventId)
    }
  }

  return { replayed, irreversible, failed }
}
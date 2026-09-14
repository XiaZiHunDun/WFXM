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
  let currentGroup: AuditEventSummary[] = [sorted[0]!]

  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i]!.ts - sorted[i - 1]!.ts > SEQUENCE_GAP_MS) {
      if (currentGroup.length >= DEFAULT_COUNT_THRESHOLD) {
        sequences.push({
          start_ts: currentGroup[0]!.ts,
          end_ts: currentGroup[currentGroup.length - 1]!.ts,
          count: currentGroup.length,
          event_ids: currentGroup.map(e => e.event_id),
        })
      }
      currentGroup = [sorted[i]!]
    } else {
      currentGroup.push(sorted[i]!)
    }
  }
  // tail group
  if (currentGroup.length >= DEFAULT_COUNT_THRESHOLD) {
    sequences.push({
      start_ts: currentGroup[0]!.ts,
      end_ts: currentGroup[currentGroup.length - 1]!.ts,
      count: currentGroup.length,
      event_ids: currentGroup.map(e => e.event_id),
    })
  }
  // sort DESC by start_ts
  return sequences.sort((a, b) => b.start_ts - a.start_ts)
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
  const failed: Array<{ event_id: string; reason: string }> = []

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
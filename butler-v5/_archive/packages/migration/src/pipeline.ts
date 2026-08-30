import { makeV4Source, type V4AssetKind, type V4Record } from "./v4-source.js"
import type { EventBridge } from "@butler/persistence/event-bridge.js"

export interface MigrationConfig {
  readonly v4Root: string
  readonly bridge: EventBridge
  readonly dryRun: boolean
}

export interface MigrationSuccess {
  readonly ok: true
  readonly eventsWritten: number
  readonly skipped: number
}

export interface MigrationFailure {
  readonly ok: false
  readonly reason: string
}

export type MigrationOutput = MigrationSuccess | MigrationFailure

const KINDS: readonly V4AssetKind[] = [
  "conversation",
  "memory",
  "task",
  "approval",
  "skill",
  "experience",
]

/**
 * Run the migration pipeline.
 *  - Reads each kind from the v4 source.
 *  - Maps each record to a domain event.
 *  - Writes events via the EventBridge (bridge.appendConversationEvent handles stream versioning internally).
 *  - Idempotent: re-running produces the same effective state.
 *  - Dry run: skips actual event appends but reports the count.
 *  - No throw — returns MigrationOutput.
 */
export async function runMigration(config: MigrationConfig): Promise<MigrationOutput> {
  if (typeof config.v4Root !== "string" || config.v4Root.length === 0) {
    return { ok: false, reason: "v4Root must be a non-empty string" }
  }
  try {
    const source = makeV4Source({ v4Root: config.v4Root })
    let written = 0
    let skipped = 0
    for (const kind of KINDS) {
      const res = await source.readAll(kind)
      if (!res.ok) return { ok: false, reason: res.reason }
      for (const record of res.records) {
        if (config.dryRun) {
          skipped++
          continue
        }
        const streamId = deriveStreamId(record)
        await config.bridge.appendConversationEvent({
          streamId,
          event: recordToEvent(record),
          eventId: `${streamId}-${record.kind}`,
          eventType: `${record.kind}Imported`,
          correlationId: "r6-migration",
          actor: { kind: "system", id: "migration" },
        })
        written++
      }
    }
    return { ok: true, eventsWritten: written, skipped }
  } catch (err) {
    return { ok: false, reason: err instanceof Error ? err.message : String(err) }
  }
}

function deriveStreamId(record: V4Record): string {
  switch (record.kind) {
    case "conversation":
      return `c-${record.id}`
    case "memory":
      return `m-${record.projectId}-${record.text.slice(0, 16)}`
    case "task":
      return `t-${record.taskId}`
    case "approval":
      return `a-${record.projectId}-${record.fingerprint}`
    case "skill":
      return `s-${record.projectId}-${record.name}`
    case "experience":
      return `e-${record.projectId}-${record.id}`
  }
}

function recordToEvent(record: V4Record): unknown {
  return { _tag: `${record.kind}Imported`, payload: record }
}

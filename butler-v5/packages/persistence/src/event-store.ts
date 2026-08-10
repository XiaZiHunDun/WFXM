import { eq, max } from "drizzle-orm"
import type { PgliteDatabase } from "drizzle-orm/pglite"
import { eventStore } from "./schema.js"

export class OptimisticConcurrencyError extends Error {
  constructor(
    public readonly streamId: string,
    public readonly expectedVersion: number,
  ) {
    super(
      `optimistic concurrency conflict on stream ${streamId} at expected version ${expectedVersion}`,
    )
  }
}

export interface ActorRef {
  readonly kind: "owner" | "agent" | "system"
  readonly id: string
}

export interface EnvelopeInput {
  readonly eventId: string
  readonly eventType: string
  readonly eventVersion: number
  readonly correlationId: string
  readonly occurredAt: Date
  readonly actor: ActorRef
}

export type EventStoreRow = typeof eventStore.$inferSelect

// UUID v4 format: 8-4-4-4-12 hex chars. Lets us accept either a pre-generated
// UUID from the caller or any logical string id (test data uses "e1", "e2").
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/**
 * Convert a caller-supplied eventId into the UUID primary key stored in
 * event_store.event_id. If the caller already provides a UUID we use it
 * as-is; otherwise we mint a fresh random UUID so the schema's uuid column
 * accepts the value without forcing callers to pre-generate UUIDs upstream.
 */
function toEventUuid(eventId: string): string {
  return UUID_RE.test(eventId) ? eventId : crypto.randomUUID()
}

/**
 * Returns the next available streamVersion for a stream (1 if empty).
 */
export async function nextVersion(
  db: PgliteDatabase<Record<string, never>>,
  streamId: string,
): Promise<number> {
  const rows = await db
    .select({ max: max(eventStore.streamVersion) })
    .from(eventStore)
    .where(eq(eventStore.streamId, streamId))
  const m = rows[0]?.max
  return (m ?? 0) + 1
}

/**
 * Append an event to a stream. streamVersion must be monotonically increasing;
 * conflicts throw OptimisticConcurrencyError so the caller can retry with a
 * fresh version.
 */
export async function appendEvents(
  db: PgliteDatabase<Record<string, never>>,
  streamId: string,
  event: unknown,
  envelope: EnvelopeInput,
): Promise<void> {
  const expectedVersion = envelope.eventVersion
  const version = await nextVersion(db, streamId)
  if (version !== expectedVersion) {
    throw new OptimisticConcurrencyError(streamId, expectedVersion)
  }
  await db.insert(eventStore).values({
    eventId: toEventUuid(envelope.eventId),
    streamId,
    streamType: "conversation",
    streamVersion: version,
    eventType: envelope.eventType,
    eventVersion: envelope.eventVersion,
    payload: event,
    occurredAt: envelope.occurredAt,
    causationId: null,
    correlationId: envelope.correlationId,
    actorKind: envelope.actor.kind,
    actorId: envelope.actor.id,
  })
}

/**
 * Load all events for a stream in streamVersion ascending order.
 */
export async function loadStream(
  db: PgliteDatabase<Record<string, never>>,
  streamId: string,
): Promise<EventStoreRow[]> {
  return db
    .select()
    .from(eventStore)
    .where(eq(eventStore.streamId, streamId))
    .orderBy(eventStore.streamVersion)
}

/**
 * Long-poll style subscription: invokes handler for each newly appended event
 * on the given stream. Polls every 25ms; cancel via the returned function.
 */
export function subscribeStream(
  db: PgliteDatabase<Record<string, never>>,
  streamId: string,
  handler: (e: EventStoreRow) => void,
): () => void {
  let lastVersion = 0
  let stopped = false
  const tick = async () => {
    if (stopped) return
    const rows = await loadStream(db, streamId)
    for (const row of rows) {
      if (row.streamVersion > lastVersion) {
        lastVersion = row.streamVersion
        handler(row)
      }
    }
    setTimeout(tick, 25)
  }
  setTimeout(tick, 0)
  return () => {
    stopped = true
  }
}

import { eq, max } from "drizzle-orm"
import type { ButlerDb } from "./db.js"
import { enqueueOutbox, type EnqueueInput } from "./outbox.js"
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

/** Caller may omit eventVersion; it is assigned inside the append transaction. */
export type EnvelopeInputFlexible = Omit<EnvelopeInput, "eventVersion"> & {
  readonly eventVersion?: number
}

const DEFAULT_APPEND_RETRIES = 3

function isUniqueViolation(err: unknown): boolean {
  if (!(err instanceof Error)) return false
  const msg = err.message.toLowerCase()
  return msg.includes("unique") || msg.includes("duplicate")
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
export async function nextVersion(db: ButlerDb, streamId: string): Promise<number> {
  const rows = await db
    .select({ max: max(eventStore.streamVersion) })
    .from(eventStore)
    .where(eq(eventStore.streamId, streamId))
  const m = rows[0]?.max
  return (m ?? 0) + 1
}

async function appendEventsInTx(
  tx: ButlerDb,
  streamId: string,
  event: unknown,
  envelope: EnvelopeInputFlexible,
): Promise<number> {
  const version = await nextVersion(tx, streamId)
  if (envelope.eventVersion !== undefined && envelope.eventVersion !== version) {
    throw new OptimisticConcurrencyError(streamId, envelope.eventVersion)
  }
  await tx.insert(eventStore).values({
    eventId: toEventUuid(envelope.eventId),
    streamId,
    streamType: "conversation",
    streamVersion: version,
    eventType: envelope.eventType,
    eventVersion: version,
    payload: event,
    occurredAt: envelope.occurredAt,
    causationId: null,
    correlationId: envelope.correlationId,
    actorKind: envelope.actor.kind,
    actorId: envelope.actor.id,
  })
  return version
}

/**
 * Append an event to a stream inside a single DB transaction. When the caller
 * supplies eventVersion it must match the next stream version; otherwise
 * OptimisticConcurrencyError is thrown.
 */
export async function appendEvents(
  db: ButlerDb,
  streamId: string,
  event: unknown,
  envelope: EnvelopeInput,
): Promise<void> {
  await db.transaction(async (tx) => {
    await appendEventsInTx(tx, streamId, event, envelope)
  })
}

/**
 * Append with bounded retry on unique-index races. eventVersion is optional;
 * each attempt re-reads the next version inside a fresh transaction.
 */
export async function appendEventsWithRetry(
  db: ButlerDb,
  streamId: string,
  event: unknown,
  envelope: EnvelopeInputFlexible,
  maxAttempts = DEFAULT_APPEND_RETRIES,
): Promise<void> {
  let lastError: unknown
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      await db.transaction(async (tx) => {
        await appendEventsInTx(tx, streamId, event, envelope)
      })
      return
    } catch (err) {
      lastError = err
      if (err instanceof OptimisticConcurrencyError) throw err
      if (!isUniqueViolation(err) || attempt === maxAttempts - 1) throw err
    }
  }
  throw lastError
}

/**
 * Atomically append a domain event and enqueue its outbox message. Rolls back
 * both writes if either step fails.
 */
export async function appendEventAndEnqueueOutbox(
  db: ButlerDb,
  streamId: string,
  event: unknown,
  envelope: EnvelopeInputFlexible,
  outboxInput: EnqueueInput,
): Promise<string> {
  return db.transaction(async (tx) => {
    await appendEventsInTx(tx, streamId, event, envelope)
    return enqueueOutbox(tx, outboxInput)
  })
}

/**
 * Load all events for a stream in streamVersion ascending order.
 */
export async function loadStream(db: ButlerDb, streamId: string): Promise<EventStoreRow[]> {
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
  db: ButlerDb,
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

import { eq } from "drizzle-orm"
import type { ButlerDb } from "./db.js"
import { projections } from "./schema.js"
import { loadStream, type EventStoreRow } from "./event-store.js"

export type Handler = (event: EventStoreRow) => Promise<void>

const registry = new Map<string, Handler>()

/**
 * Register a projection handler by name. Replaces any prior handler with
 * the same name (idempotent for test re-runs).
 */
export function registerProjection(name: string, handler: Handler): void {
  registry.set(name, handler)
}

/**
 * Apply the projection to all events in a stream, then bump the
 * persisted projection version to the latest streamVersion processed.
 */
export async function applyProjection(
  db: ButlerDb,
  streamId: string,
  projectionName: string,
): Promise<void> {
  const handler = registry.get(projectionName)
  if (!handler) throw new Error(`unknown projection: ${projectionName}`)
  const events = await loadStream(db, streamId)
  for (const e of events) {
    await handler(e)
  }
  const last = events.at(-1)?.streamVersion ?? 0
  await db
    .insert(projections)
    .values({ projectionName, version: last, state: {}, updatedAt: new Date() })
    .onConflictDoUpdate({
      target: projections.projectionName,
      set: { version: last, updatedAt: new Date() },
    })
}

/**
 * Wipe the projection's persisted state and replay all events for the stream.
 * Use when handler logic changes or data drifts.
 */
export async function rebuildProjection(
  db: ButlerDb,
  streamId: string,
  projectionName: string,
): Promise<void> {
  await db.delete(projections).where(eq(projections.projectionName, projectionName))
  await applyProjection(db, streamId, projectionName)
}

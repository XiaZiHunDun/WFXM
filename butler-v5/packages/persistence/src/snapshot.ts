import { eq } from "drizzle-orm"
import type { PgliteDatabase } from "drizzle-orm/pglite"
import { snapshots } from "./schema.js"

export type Snapshot = typeof snapshots.$inferSelect

/**
 * Save or replace the snapshot for a stream. Last writer wins; a more
 * recent streamVersion overwrites an older one.
 */
export async function saveSnapshot(
  db: PgliteDatabase<Record<string, never>>,
  streamId: string,
  streamVersion: number,
  payload: Record<string, unknown>,
): Promise<void> {
  await db
    .insert(snapshots)
    .values({ streamId, streamVersion, payload, takenAt: new Date() })
    .onConflictDoUpdate({
      target: snapshots.streamId,
      set: { streamVersion, payload, takenAt: new Date() },
    })
}

/**
 * Load the current snapshot for a stream, or null if none exists.
 */
export async function loadSnapshot(
  db: PgliteDatabase<Record<string, never>>,
  streamId: string,
): Promise<Snapshot | null> {
  const rows = await db.select().from(snapshots).where(eq(snapshots.streamId, streamId))
  return rows[0] ?? null
}

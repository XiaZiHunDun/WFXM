import type { PgliteDatabase } from "drizzle-orm/pglite"
import type { NodePgDatabase } from "drizzle-orm/node-postgres"

/**
 * Drizzle handle used by event_store / outbox. PGlite for tests and
 * local defaults; node-postgres for the durable production path.
 */
export type ButlerDb = PgliteDatabase<Record<string, never>> | NodePgDatabase<Record<string, never>>

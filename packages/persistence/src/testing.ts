import { PGlite } from "@electric-sql/pglite"
import { drizzle, type PgliteDatabase } from "drizzle-orm/pglite"
import { applyMigrations } from "./migrations/run-migrations.js"
import * as schema from "./schema.js"

export type TestDb = PgliteDatabase<Record<string, never>> & {
  readonly pg: PGlite
  readonly close: () => Promise<void>
  readonly db: PgliteDatabase<Record<string, never>>
}

/**
 * pglite-backed Drizzle client for in-process unit tests.
 * Each test gets a fresh in-memory Postgres — no container required.
 */
export async function makeTestDb(): Promise<TestDb> {
  const pg = new PGlite()
  await applyMigrations((sql) => pg.exec(sql))
  const drizzleDb = drizzle(pg, { schema })
  return Object.create(drizzleDb, {
    pg: { value: pg, enumerable: true },
    db: { value: drizzleDb, enumerable: true },
    close: { value: () => pg.close(), enumerable: true },
  }) as TestDb
}

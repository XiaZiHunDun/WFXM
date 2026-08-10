import { PGlite } from "@electric-sql/pglite"
import { drizzle, type PgliteDatabase } from "drizzle-orm/pglite"
import * as schema from "./schema.js"

export type TestDb = PgliteDatabase<Record<string, never>> & {
  readonly pg: PGlite
  readonly close: () => Promise<void>
  readonly db: PgliteDatabase<Record<string, never>>
}

/**
 * pglite-backed Drizzle client for in-process unit tests.
 * Each test gets a fresh in-memory Postgres — no container required.
 *
 * The returned object is a thin wrapper whose prototype is the Drizzle
 * instance, so callers can use it as a plain Drizzle db (`db.select()`,
 * `db.insert()`, etc.) while still reaching the underlying `pg` handle,
 * the raw `db` reference, and the lifecycle `close()` helper.
 */
export async function makeTestDb(): Promise<TestDb> {
  const pg = new PGlite()
  await pg.exec(`
    CREATE TABLE event_store (
      event_id uuid PRIMARY KEY NOT NULL,
      stream_id text NOT NULL,
      stream_type text NOT NULL,
      stream_version integer NOT NULL,
      event_type text NOT NULL,
      event_version integer NOT NULL,
      payload jsonb NOT NULL,
      occurred_at timestamptz NOT NULL,
      causation_id text,
      correlation_id text NOT NULL,
      actor_kind text NOT NULL,
      actor_id text NOT NULL
    );
    CREATE UNIQUE INDEX event_store_stream_uniq ON event_store (stream_id, stream_version);
    CREATE TABLE outbox (
      message_id uuid PRIMARY KEY NOT NULL,
      stream_id text NOT NULL,
      aggregate_type text NOT NULL,
      payload jsonb NOT NULL,
      status text NOT NULL,
      attempt_count integer NOT NULL DEFAULT 0,
      next_attempt_at timestamptz NOT NULL,
      lease_owner text,
      lease_until timestamptz,
      last_error text,
      created_at timestamptz NOT NULL,
      delivered_at timestamptz
    );
    CREATE TABLE snapshots (
      stream_id text PRIMARY KEY NOT NULL,
      stream_version integer NOT NULL,
      payload jsonb NOT NULL,
      taken_at timestamptz NOT NULL
    );
    CREATE TABLE projections (
      projection_name text PRIMARY KEY NOT NULL,
      version integer NOT NULL,
      state jsonb NOT NULL,
      updated_at timestamptz NOT NULL
    );
  `)
  const drizzleDb = drizzle(pg, { schema })
  return Object.create(drizzleDb, {
    pg: { value: pg, enumerable: true },
    db: { value: drizzleDb, enumerable: true },
    close: { value: () => pg.close(), enumerable: true },
  }) as TestDb
}

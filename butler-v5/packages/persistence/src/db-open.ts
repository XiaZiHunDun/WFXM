import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { PGlite } from "@electric-sql/pglite"
import { drizzle as drizzlePglite } from "drizzle-orm/pglite"
import { drizzle as drizzlePg } from "drizzle-orm/node-postgres"
import pg from "pg"
import type { ButlerDb } from "./db.js"
import { resolveButlerDbKind } from "./db-kind.js"

const { Pool } = pg

const MIGRATION_SQL = readFileSync(
  fileURLToPath(new URL("./migrations/0001_initial.sql", import.meta.url)),
  "utf8",
)

export type OpenedButlerDb = {
  readonly kind: "pglite" | "postgres"
  readonly db: ButlerDb
  readonly close: () => Promise<void>
}

export type OpenButlerResult =
  | { readonly ok: true; readonly value: OpenedButlerDb }
  | { readonly ok: false; readonly reason: string }

function errorReason(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

/**
 * Open the event-store database. Never throws: connection/schema failures
 * return `{ ok: false }`. Production callers should exit rather than
 * silently falling back to in-process PGlite.
 */
export async function openButlerDatabase(env: NodeJS.ProcessEnv): Promise<OpenButlerResult> {
  const kind = resolveButlerDbKind(env)
  if (kind === "pglite") {
    try {
      const client = new PGlite()
      await client.exec(MIGRATION_SQL)
      const db = drizzlePglite(client, {})
      return {
        ok: true,
        value: {
          kind,
          db,
          close: () => client.close(),
        },
      }
    } catch (err) {
      return { ok: false, reason: `pglite open failed: ${errorReason(err)}` }
    }
  }

  const url = (env["DATABASE_URL"] ?? "").trim()
  if (!url) {
    return { ok: false, reason: "BUTLER_V5_DB=postgres requires a non-empty DATABASE_URL" }
  }

  const maxRaw = Number((env["DB_MAX_CONNECTIONS"] ?? "8").trim())
  const max = Number.isFinite(maxRaw) && maxRaw > 0 ? maxRaw : 8
  const pool = new Pool({ connectionString: url, max })
  try {
    await pool.query(MIGRATION_SQL)
  } catch (err) {
    await pool.end().catch(() => undefined)
    return { ok: false, reason: `postgres open failed: ${errorReason(err)}` }
  }
  const db = drizzlePg(pool, {})
  return {
    ok: true,
    value: {
      kind: "postgres",
      db,
      close: () => pool.end(),
    },
  }
}

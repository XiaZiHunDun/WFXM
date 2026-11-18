import { PGlite } from "@electric-sql/pglite"
import { drizzle as drizzlePglite } from "drizzle-orm/pglite"
import { drizzle as drizzlePg } from "drizzle-orm/node-postgres"
import pg from "pg"
import type { ButlerDb } from "./db.js"
import { resolveButlerDbKind } from "./db-kind.js"
import { applyMigrations } from "./migrations/run-migrations.js"
import { backfillConversationProjectIds } from "./conversation-project-backfill.js"
import { resolvePgliteDataDir } from "./pglite-data-dir.js"

const { Pool } = pg

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
      const dataDir = resolvePgliteDataDir(env)
      const client = dataDir ? new PGlite(dataDir) : new PGlite()
      await applyMigrations((sql) => client.exec(sql))
      const db = drizzlePglite(client, {})
      await backfillConversationProjectIds(db)
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
    await applyMigrations((sql) => pool.query(sql))
  } catch (err) {
    await pool.end().catch(() => undefined)
    return { ok: false, reason: `postgres open failed: ${errorReason(err)}` }
  }
  const db = drizzlePg(pool, {})
  await backfillConversationProjectIds(db)
  return {
    ok: true,
    value: {
      kind: "postgres",
      db,
      close: () => pool.end(),
    },
  }
}

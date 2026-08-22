import { homedir } from "node:os"
import { join } from "node:path"

const DEFAULT_PGLITE_DIR = join(homedir(), ".butler", "v5-data")

function expandHome(path: string): string {
  if (path.startsWith("~/")) {
    return join(homedir(), path.slice(2))
  }
  return path
}

/**
 * PGlite filesystem path, or `undefined` for in-memory.
 *
 * - Tests (`NODE_ENV=test` / `VITEST`): always in-memory
 * - `BUTLER_V5_PGLITE_DATA_DIR=memory|:memory:`: in-memory
 * - unset (non-test): `~/.butler/v5-data` so local dev survives restart without Docker Postgres
 */
export function resolvePgliteDataDir(env: NodeJS.ProcessEnv): string | undefined {
  const isTest =
    (env["NODE_ENV"] ?? "").trim() === "test" || (env["VITEST"] ?? "").trim() !== ""
  if (isTest) return undefined

  const explicit = (env["BUTLER_V5_PGLITE_DATA_DIR"] ?? "").trim()
  if (explicit === "" ) {
    return DEFAULT_PGLITE_DIR
  }
  const lower = explicit.toLowerCase()
  if (lower === "memory" || lower === ":memory:") {
    return undefined
  }
  return expandHome(explicit)
}

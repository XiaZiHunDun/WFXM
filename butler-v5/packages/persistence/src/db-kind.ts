export type ButlerDbKind = "pglite" | "postgres"

/**
 * Choose the event-store backend.
 *
 * - `BUTLER_V5_DB=pglite|postgres` wins when set
 * - otherwise production (`NODE_ENV=production`) with a non-empty
 *   `DATABASE_URL` uses postgres so restarts keep conversation memory
 * - everything else (tests, local `pnpm start` without flags) stays pglite
 */
export function resolveButlerDbKind(env: NodeJS.ProcessEnv): ButlerDbKind {
  const explicit = (env["BUTLER_V5_DB"] ?? "").trim().toLowerCase()
  if (explicit === "pglite" || explicit === "memory") return "pglite"
  if (explicit === "postgres" || explicit === "pg") return "postgres"
  const url = (env["DATABASE_URL"] ?? "").trim()
  if (url && (env["NODE_ENV"] ?? "").trim() === "production") return "postgres"
  return "pglite"
}

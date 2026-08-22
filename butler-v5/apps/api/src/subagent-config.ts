/**
 * Opt-in background subagent + WS push (default off).
 *
 * BUTLER_V5_SUBAGENT_ENABLED=1
 *   → start WS server (loopback, WS_PORT default 3001) + outbox worker
 *   → expose delegate_to_subagent tool to the butler loop
 */

function envTruthy(raw: string | undefined): boolean {
  if (!raw) return false
  const text = raw.trim().toLowerCase()
  return text === "1" || text === "true" || text === "yes" || text === "on"
}

export function isSubagentEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return envTruthy(env["BUTLER_V5_SUBAGENT_ENABLED"])
}

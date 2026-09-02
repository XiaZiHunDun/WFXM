import { envTruthy } from "./env-util.js"
/**
 * Opt-in background subagent + WS push (default off).
 *
 * BUTLER_V5_SUBAGENT_ENABLED=1
 *   → start WS server (loopback, WS_PORT default 3001) + outbox worker
 *   → expose delegate_to_subagent tool to the butler loop
 */


export function isSubagentEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return envTruthy(env["BUTLER_V5_SUBAGENT_ENABLED"])
}

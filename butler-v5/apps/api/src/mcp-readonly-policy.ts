import { envTruthy } from "./env-util.js"

/** Opt-in: manifest risk=low MCP tools skip per-call Ask for owner (BUTLER_V5_MCP_READONLY_AUTO_ALLOW). */
export function isMcpReadonlyAutoAllowEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return envTruthy(env["BUTLER_V5_MCP_READONLY_AUTO_ALLOW"])
}

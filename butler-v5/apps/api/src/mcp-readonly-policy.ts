function envTruthy(raw: string | undefined): boolean {
  if (!raw) return false
  const text = raw.trim().toLowerCase()
  return text === "1" || text === "true" || text === "yes" || text === "on"
}

/** Opt-in: manifest risk=low MCP tools skip per-call Ask for owner (BUTLER_V5_MCP_READONLY_AUTO_ALLOW). */
export function isMcpReadonlyAutoAllowEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return envTruthy(env["BUTLER_V5_MCP_READONLY_AUTO_ALLOW"])
}

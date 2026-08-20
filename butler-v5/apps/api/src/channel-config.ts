import { parseCsvIds } from "./ilink-config.js"

function envTruthy(raw: string | undefined): boolean {
  if (!raw) return false
  const text = raw.trim().toLowerCase()
  return text === "1" || text === "true" || text === "yes" || text === "on"
}

/** Opt-in generic channel intake (second channel seam). Default off. */
export function isChannelApiEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return envTruthy(env["BUTLER_V5_CHANNEL_API_ENABLED"])
}

export function parseAllowedChannelIds(env: NodeJS.ProcessEnv = process.env): readonly string[] {
  const raw = (env["BUTLER_V5_CHANNEL_ALLOWLIST"] ?? "").trim()
  if (!raw) return []
  return [...new Set(parseCsvIds(raw))]
}

export function isChannelAllowed(channelId: string, allowlist: readonly string[]): boolean {
  if (allowlist.length === 0) return true
  return allowlist.includes(channelId.trim())
}

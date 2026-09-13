import { parseCsvIds } from "./ilink-config.js"
import { envTruthy } from "./env-util.js"


/** Opt-in generic channel intake (second channel seam). Default off. */
export function isChannelApiEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return envTruthy(env["BUTLER_V5_CHANNEL_API_ENABLED"])
}

export function isSlackChannelEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return envTruthy(env["BUTLER_V5_SLACK_ENABLED"])
}

export function isTelegramChannelEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return envTruthy(env["BUTLER_V5_TELEGRAM_ENABLED"])
}

export function parseAllowedChannelIds(env: NodeJS.ProcessEnv = process.env): readonly string[] {
  const raw = (env["BUTLER_V5_CHANNEL_ALLOWLIST"] ?? "").trim()
  if (!raw) return []
  return [...new Set(parseCsvIds(raw))]
}

export function isChannelAllowed(channelId: string, allowlist: readonly string[]): boolean {
  // D63 T4 (audit #9 F-02): FAIL-OPEN → FAIL-CLOSED. Empty allowlist
  // previously meant "any channelId accepted". For the generic channel
  // intake seam, this is dangerous: any channelId a network-reachable
  // attacker chooses would pass. Invert: empty allowlist = DENY. Operator
  // must explicitly populate BUTLER_V5_CHANNEL_ALLOWLIST to allow
  // channels. D61 F-25 noted the FAIL-OPEN pattern; this cycle promotes
  // to must-fix because the channel API is now a primary surface (R8.x).
  if (allowlist.length === 0) return false
  return allowlist.includes(channelId.trim())
}

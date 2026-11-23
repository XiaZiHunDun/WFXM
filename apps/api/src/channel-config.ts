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

/** Inbound pipeline a channel routes to. Default is the legacy RunEngine. */
export type ChannelEngine = "legacy" | "butler"

function channelEngineKey(channelId: string): string {
  const normalized = channelId
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "_")
  return `BUTLER_V5_${normalized}_ENGINE`
}

/**
 * Per-channel cutover switch.
 *
 * `BUTLER_V5_<CHANNEL>_ENGINE` wins over the shared
 * `BUTLER_V5_CHANNEL_ENGINE`; only "butler" opts in, everything else
 * (missing / typo / "legacy") keeps the legacy pipeline.
 */
export function resolveChannelEngine(env: NodeJS.ProcessEnv, channelId: string): ChannelEngine {
  const specific = (env[channelEngineKey(channelId)] ?? "").trim().toLowerCase()
  if (specific) return specific === "butler" ? "butler" : "legacy"
  const shared = (env["BUTLER_V5_CHANNEL_ENGINE"] ?? "").trim().toLowerCase()
  return shared === "butler" ? "butler" : "legacy"
}

/**
 * Project a channel inbound turn belongs to.
 *
 * `BUTLER_V5_CHANNEL_PROJECTS` is a JSON object (channelId -> projectId);
 * unmatched channels fall back to `BUTLER_V5_DEFAULT_PROJECT_ID`, then
 * "wechat". Malformed JSON is treated as unset so a typo cannot drop
 * inbound traffic.
 */
export function resolveChannelProjectId(
  channelId: string,
  env: NodeJS.ProcessEnv = process.env,
): string {
  const raw = (env["BUTLER_V5_CHANNEL_PROJECTS"] ?? "").trim()
  if (raw) {
    try {
      const parsed: unknown = JSON.parse(raw)
      if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) {
        const mapped = (parsed as Record<string, unknown>)[channelId.trim()]
        if (typeof mapped === "string" && mapped.trim()) return mapped.trim()
      }
    } catch {
      // Fall through to the default project.
    }
  }
  const fallback = (env["BUTLER_V5_DEFAULT_PROJECT_ID"] ?? "").trim()
  return fallback || "wechat"
}

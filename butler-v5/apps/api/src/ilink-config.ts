import { homedir } from "node:os"
import { join } from "node:path"
import { DEFAULT_ILINK_BASE_URL, type ILinkResult } from "@butler/adapters"

function envTruthy(raw: string | undefined): boolean {
  if (!raw) return false
  const text = raw.trim().toLowerCase()
  return text === "1" || text === "true" || text === "yes" || text === "on"
}

export type DmPolicy = "open" | "allowlist" | "disabled"

export type IlinkPollerConfig = {
  readonly baseUrl: string
  readonly token: string
  readonly accountId: string
  readonly inboundUrl: string
  readonly inboundTimeoutMs: number
  readonly longPollTimeoutMs: number
  readonly emptyPollDelayMs: number
  readonly sessionExpiredSleepMs: number
  readonly dmPolicy: DmPolicy
  readonly allowedUserIds: readonly string[]
  readonly dropGroups: boolean
  readonly syncBufPath: string
}

export function parseCsvIds(raw: string | undefined): string[] {
  if (!raw) return []
  return raw
    .split(/[,\s]+/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0)
}

export function parseDmPolicy(raw: string | undefined): DmPolicy {
  const policy = (raw ?? "open").trim().toLowerCase()
  if (policy === "allowlist" || policy === "disabled" || policy === "open") {
    return policy
  }
  return "open"
}

export function isDmAllowed(
  senderId: string,
  policy: DmPolicy,
  allowedUserIds: readonly string[],
): boolean {
  if (policy === "disabled") return false
  if (policy === "allowlist") return allowedUserIds.includes(senderId)
  return true
}

export function parseIlinkPollerConfig(env: NodeJS.ProcessEnv): ILinkResult<IlinkPollerConfig> {
  if (!envTruthy(env["BUTLER_V5_ILINK_ENABLED"])) {
    return { ok: false, reason: "BUTLER_V5_ILINK_ENABLED is off" }
  }
  const token = (env["WECHAT_TOKEN"] ?? "").trim()
  if (!token) {
    return { ok: false, reason: "WECHAT_TOKEN is required when iLink is enabled" }
  }
  const baseUrl = (env["WECHAT_BASE_URL"] ?? env["ILINK_BASE_URL"] ?? DEFAULT_ILINK_BASE_URL).trim()
  const port = (env["PORT"] ?? "3000").trim() || "3000"
  const inboundUrl = (env["V5_INBOUND_URL"] ?? `http://127.0.0.1:${port}/v1/wechat/inbound`).trim()
  const inboundTimeoutMs = Number(env["BUTLER_V5_ILINK_INBOUND_TIMEOUT_MS"] ?? 180_000)
  const longPollTimeoutMs = Number(env["BUTLER_V5_ILINK_LONG_POLL_MS"] ?? 35_000)
  const emptyPollDelayMs = Number(env["BUTLER_V5_ILINK_EMPTY_DELAY_MS"] ?? 250)
  const sessionExpiredSleepMs = Number(env["BUTLER_V5_ILINK_SESSION_SLEEP_MS"] ?? 600_000)
  const allowedUserIds = [
    ...parseCsvIds(env["WECHAT_ALLOWED_USERS"]),
    ...parseCsvIds(env["BUTLER_OWNER_WECHAT_ID"]),
  ]
  const uniqueAllowed = [...new Set(allowedUserIds)]
  const syncBufPath = (
    env["BUTLER_V5_ILINK_SYNC_BUF_PATH"] ??
    join(homedir(), ".config", "butler-v5", "ilink-sync.json")
  ).trim()
  return {
    ok: true,
    value: {
      baseUrl,
      token,
      accountId: (env["WECHAT_ACCOUNT_ID"] ?? "").trim(),
      inboundUrl,
      inboundTimeoutMs: Number.isFinite(inboundTimeoutMs) ? inboundTimeoutMs : 180_000,
      longPollTimeoutMs: Number.isFinite(longPollTimeoutMs) ? longPollTimeoutMs : 35_000,
      emptyPollDelayMs: Number.isFinite(emptyPollDelayMs) ? emptyPollDelayMs : 250,
      sessionExpiredSleepMs: Number.isFinite(sessionExpiredSleepMs)
        ? sessionExpiredSleepMs
        : 600_000,
      dmPolicy: parseDmPolicy(env["WECHAT_DM_POLICY"]),
      allowedUserIds: uniqueAllowed,
      dropGroups: env["WECHAT_GROUP_POLICY"]?.trim().toLowerCase() === "open" ? false : true,
      syncBufPath,
    },
  }
}

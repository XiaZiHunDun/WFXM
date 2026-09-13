import { homedir } from "node:os"
import { envTruthy, parsePositiveInt } from "./env-util.js"
import { join } from "node:path"
import {
  DEFAULT_ILINK_BASE_URL,
  DEFAULT_WECHAT_CDN_BASE_URL,
  type ILinkResult,
} from "@butler/adapters"


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
  readonly cdnBaseUrl: string
  readonly mediaCacheDir: string
  readonly mediaMaxBytes: number
}

export function parseCsvIds(raw: string | undefined): string[] {
  if (!raw) return []
  return raw
    .split(/[,\s]+/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0)
}

function parseDmPolicy(raw: string | undefined): DmPolicy {
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
  const allowedUserIds = [
    ...parseCsvIds(env["WECHAT_ALLOWED_USERS"]),
    ...parseCsvIds(env["BUTLER_OWNER_WECHAT_ID"]),
  ]
  const uniqueAllowed = [...new Set(allowedUserIds)]
  const syncBufPath = (
    env["BUTLER_V5_ILINK_SYNC_BUF_PATH"] ??
    join(homedir(), ".config", "butler-v5", "ilink-sync.json")
  ).trim()
  const workspaceRoot = (env["BUTLER_V5_WORKSPACE_ROOT"] ?? process.cwd()).trim()
  // D60 T4.3 (audit #1 F-16/F-28/F-29): clamp operator-supplied media-size
// env var to the 100MB safety cap so a typo (e.g. =999999999999) can't
// bypass the gate.
const MAX_MEDIA_BYTES_CAP = 100 * 1024 * 1024
const rawMaxBytes = Number(env["WECHAT_MEDIA_MAX_BYTES"] ?? 8 * 1024 * 1024)
const mediaMaxBytes =
  Number.isFinite(rawMaxBytes) && rawMaxBytes > 0
    ? Math.min(rawMaxBytes, MAX_MEDIA_BYTES_CAP)
    : 8 * 1024 * 1024
  return {
    ok: true,
    value: {
      baseUrl,
      token,
      accountId: (env["WECHAT_ACCOUNT_ID"] ?? "").trim(),
      inboundUrl,
      inboundTimeoutMs: parsePositiveInt(env["BUTLER_V5_ILINK_INBOUND_TIMEOUT_MS"], 180_000),
      longPollTimeoutMs: parsePositiveInt(env["BUTLER_V5_ILINK_LONG_POLL_MS"], 35_000),
      emptyPollDelayMs: parsePositiveInt(env["BUTLER_V5_ILINK_EMPTY_DELAY_MS"], 250),
      sessionExpiredSleepMs: parsePositiveInt(env["BUTLER_V5_ILINK_SESSION_SLEEP_MS"], 600_000),
      dmPolicy: parseDmPolicy(env["WECHAT_DM_POLICY"]),
      allowedUserIds: uniqueAllowed,
      dropGroups: env["WECHAT_GROUP_POLICY"]?.trim().toLowerCase() === "open" ? false : true,
      syncBufPath,
      cdnBaseUrl: (env["WECHAT_CDN_BASE_URL"] ?? DEFAULT_WECHAT_CDN_BASE_URL).trim(),
      mediaCacheDir: join(workspaceRoot, ".butler", "ilink-media"),
      mediaMaxBytes:
        Number.isFinite(mediaMaxBytes) && mediaMaxBytes > 0 ? mediaMaxBytes : 8 * 1024 * 1024,
    },
  }
}

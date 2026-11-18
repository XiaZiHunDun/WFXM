import { mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { dirname } from "node:path"

export type WechatEnvCreds = {
  readonly token: string
  readonly accountId: string
  readonly baseUrl: string
}

const MANAGED_KEYS = new Set([
  "WECHAT_TOKEN",
  "WECHAT_ACCOUNT_ID",
  "WECHAT_BASE_URL",
  "BUTLER_V5_ILINK_ENABLED",
])

export function upsertWechatEnvFile(path: string, creds: WechatEnvCreds): void {
  let raw = ""
  try {
    raw = readFileSync(path, "utf8")
  } catch {
    raw = ""
  }
  const keep: string[] = []
  for (const line of raw.split(/\r?\n/)) {
    const stripped = line.trim()
    const key = stripped.includes("=") && !stripped.startsWith("#") ? stripped.split("=", 1)[0] : ""
    if (key && MANAGED_KEYS.has(key)) continue
    keep.push(line)
  }
  while (keep.length > 0 && keep[keep.length - 1] === "") {
    keep.pop()
  }
  const block = [
    "",
    "# Native iLink credentials (butler wechat-login)",
    "BUTLER_V5_ILINK_ENABLED=1",
    `WECHAT_TOKEN=${creds.token}`,
    `WECHAT_ACCOUNT_ID=${creds.accountId}`,
    `WECHAT_BASE_URL=${creds.baseUrl}`,
  ]
  mkdirSync(dirname(path), { recursive: true })
  writeFileSync(path, `${[...keep, ...block].join("\n")}\n`, { encoding: "utf8", mode: 0o600 })
}

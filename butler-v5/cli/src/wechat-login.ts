import {
  DEFAULT_ILINK_BASE_URL,
  ilinkGetBotQr,
  ilinkGetQrStatus,
  interpretQrStatus,
  Secret,
  upsertWechatEnvFile,
  WECHAT_OUTBOUND_NETWORK_HOST_SET,
} from "@butler/adapters"

export type WechatLoginOpts = {
  readonly baseUrl?: string
  readonly envPath: string
  readonly timeoutMs?: number
  readonly pollMs?: number
  readonly fetch?: typeof fetch
  readonly sleep?: (ms: number) => Promise<void>
  readonly log?: (msg: string) => void
  readonly now?: () => number
}

/**
 * D70 T4 (audit #11 SEC-001): QR-confirmed baseUrl flows into all
 * subsequent iLink calls. Validate against the WeChat outbound host
 * allowlist before persisting — a compromised / malicious QR-status
 * response could redirect all outbound traffic to attacker-controlled
 * infrastructure. Same host set used by `assertWechatCdnUrl` for media.
 */
function isAllowedIlinkHost(candidate: string): boolean {
  let parsed: URL
  try {
    parsed = new URL(candidate)
  } catch {
    return false
  }
  const scheme = parsed.protocol.replace(":", "").toLowerCase()
  if (scheme !== "http" && scheme !== "https") return false
  return WECHAT_OUTBOUND_NETWORK_HOST_SET.has(parsed.hostname.toLowerCase())
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

export async function runWechatLogin(
  opts: WechatLoginOpts,
): Promise<
  | { readonly ok: true; readonly accountId: string }
  | { readonly ok: false; readonly reason: string }
> {
  const log =
    opts.log ??
    ((msg) => {
      // eslint-disable-next-line no-console -- CLI operator output
      console.log(msg)
    })
  const sleep = opts.sleep ?? delay
  const now = opts.now ?? Date.now
  const baseUrl = (opts.baseUrl ?? DEFAULT_ILINK_BASE_URL).replace(/\/+$/, "")
  const client = { baseUrl, ...(opts.fetch ? { fetch: opts.fetch } : {}) }
  const qr = await ilinkGetBotQr(client)
  if (!qr.ok) {
    return { ok: false, reason: qr.reason }
  }
  const qrcode = String(qr.value["qrcode"] ?? "")
  const qrUrl = String(qr.value["qrcode_img_content"] ?? qrcode)
  if (!qrcode) {
    return { ok: false, reason: "QR response missing qrcode" }
  }
  log("请使用微信扫描以下二维码：")
  log(qrUrl)

  const deadline = now() + (opts.timeoutMs ?? 480_000)
  const pollMs = opts.pollMs ?? 1_000
  let currentBase = baseUrl
  while (now() < deadline) {
    const status = await ilinkGetQrStatus({ ...client, baseUrl: currentBase }, qrcode)
    if (!status.ok) {
      await sleep(pollMs)
      continue
    }
    const action = interpretQrStatus(status.value)
    if (action.kind === "redirect" && action.host) {
      currentBase = action.host.startsWith("http") ? action.host : `https://${action.host}`
      continue
    }
    if (action.kind === "expired") {
      return { ok: false, reason: "QR expired" }
    }
    if (action.kind === "confirmed") {
      if (!action.accountId || !action.token) {
        return { ok: false, reason: "QR confirmed but credential payload incomplete" }
      }
      // D72 T3 (audit #18 SEC-002): unwrap the bot_token at the legitimate
      // consumption point (env file write). Secret<>.toString() returns
      // "[REDACTED]" so any accidental log() above this line leaks the
      // wrapper shape, not the cleartext token.
      const botToken = action.token.unwrap()
      const confirmedBase = action.baseUrl || currentBase
      // D70 T4 (audit #11 SEC-001): refuse to persist a baseUrl pointing
      // outside the WeChat allowlist. Persisting the unvalidated URL
      // would write the attacker-controlled host into the env file,
      // and every subsequent ilinkGet / ilinkPost would route to it.
      if (!isAllowedIlinkHost(confirmedBase)) {
        return {
          ok: false,
          reason: `QR-confirmed baseUrl ${confirmedBase} is not a WeChat iLink host; refusing to persist`,
        }
      }
      upsertWechatEnvFile(opts.envPath, {
        token: botToken,
        accountId: action.accountId,
        baseUrl: confirmedBase,
      })
      log(`微信连接成功，account_id=${action.accountId}`)
      log(`已写入 ${opts.envPath}（不含日志打印 token）。请重启 butler-v5-gateway。`)
      return { ok: true, accountId: action.accountId }
    }
    await sleep(pollMs)
  }
  return { ok: false, reason: "微信登录超时" }
}

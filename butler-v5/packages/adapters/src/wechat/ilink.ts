import {
  buildGetUpdatesBody,
  buildIlinkHeaders,
  buildSendMessageBody,
  EP_GET_BOT_QR,
  EP_GET_QR_STATUS,
  EP_GET_UPDATES,
  EP_SEND_MESSAGE,
  ILINK_APP_CLIENT_VERSION,
  ILINK_APP_ID,
  type ILinkResult,
} from "./ilink-protocol.js"

export {
  buildGetUpdatesBody,
  buildIlinkHeaders,
  buildSendMessageBody,
  CHANNEL_VERSION,
  DEFAULT_ILINK_BASE_URL,
  EP_GET_BOT_QR,
  EP_GET_QR_STATUS,
  EP_GET_UPDATES,
  EP_SEND_MESSAGE,
  extractIlinkContent,
  extractIlinkMediaPlaceholder,
  extractIlinkText,
  extractIlinkVoiceText,
  ILINK_APP_CLIENT_VERSION,
  ILINK_APP_ID,
  inboundFromIlinkMsg,
  isIlinkGroupMessage,
  isIlinkOk,
  isSessionExpired,
  ITEM_FILE,
  ITEM_IMAGE,
  ITEM_TEXT,
  ITEM_VIDEO,
  ITEM_VOICE,
  MSG_STATE_FINISH,
  MSG_TYPE_BOT,
  SESSION_EXPIRED_ERRCODE,
} from "./ilink-protocol.js"
export type { ILinkResult, IlinkInbound } from "./ilink-protocol.js"
export {
  DEFAULT_WECHAT_CDN_BASE_URL,
  describeSavedMedia,
  downloadAndCacheIlinkMedia,
  enrichIlinkInboundContent,
  extractIlinkMediaRef,
} from "./ilink-media.js"
export type { IlinkMediaDownloadConfig, IlinkMediaKind, IlinkMediaRef } from "./ilink-media.js"
export { makeTranscribeVoice, transcribeDashscopeFile, DASHSCOPE_ASR_URL } from "./ilink-asr.js"

export type ILinkClientConfig = {
  readonly baseUrl: string
  readonly token: string
  readonly fetch?: typeof fetch
  readonly longPollTimeoutMs?: number
}

function joinUrl(baseUrl: string, endpoint: string): string {
  return `${baseUrl.replace(/\/+$/, "")}/${endpoint}`
}

async function readJson(res: Response): Promise<ILinkResult<Record<string, unknown>>> {
  const raw = await res.text()
  if (!res.ok) {
    return { ok: false, reason: `HTTP ${res.status}: ${raw.slice(0, 200)}` }
  }
  try {
    const parsed: unknown = JSON.parse(raw)
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { ok: false, reason: "iLink response is not a JSON object" }
    }
    return { ok: true, value: parsed as Record<string, unknown> }
  } catch {
    return { ok: false, reason: `iLink returned non-JSON: ${raw.slice(0, 200)}` }
  }
}

export async function ilinkPost(
  config: ILinkClientConfig,
  endpoint: string,
  body: string,
  timeoutMs: number,
): Promise<ILinkResult<Record<string, unknown>>> {
  const fetchImpl = config.fetch ?? fetch
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const res = await fetchImpl(joinUrl(config.baseUrl, endpoint), {
      method: "POST",
      headers: buildIlinkHeaders(config.token),
      body,
      signal: ctrl.signal,
    })
    return await readJson(res)
  } catch (err: unknown) {
    const name = err instanceof Error ? err.name : ""
    if (name === "AbortError" || name === "TimeoutError") {
      return { ok: false, reason: "timeout" }
    }
    return { ok: false, reason: err instanceof Error ? err.message : String(err) }
  } finally {
    clearTimeout(timer)
  }
}

export async function ilinkGetUpdates(
  config: ILinkClientConfig,
  syncBuf: string,
): Promise<ILinkResult<Record<string, unknown>>> {
  const timeoutMs = config.longPollTimeoutMs ?? 35_000
  const result = await ilinkPost(config, EP_GET_UPDATES, buildGetUpdatesBody(syncBuf), timeoutMs)
  if (!result.ok && result.reason === "timeout") {
    return { ok: true, value: { ret: 0, msgs: [], get_updates_buf: syncBuf } }
  }
  return result
}

export async function ilinkSendMessage(
  config: ILinkClientConfig,
  input: { readonly to: string; readonly text: string; readonly contextToken?: string },
): Promise<ILinkResult<Record<string, unknown>>> {
  const text = input.text.trim()
  if (!text) {
    return { ok: false, reason: "send text must not be empty" }
  }
  return ilinkPost(
    config,
    EP_SEND_MESSAGE,
    buildSendMessageBody({
      to: input.to,
      text,
      clientId: `v5-${Date.now()}`,
      ...(input.contextToken ? { contextToken: input.contextToken } : {}),
    }),
    15_000,
  )
}

function buildIlinkGetHeaders(): Record<string, string> {
  return {
    "iLink-App-Id": ILINK_APP_ID,
    "iLink-App-ClientVersion": String(ILINK_APP_CLIENT_VERSION),
  }
}

export async function ilinkGet(
  config: Pick<ILinkClientConfig, "baseUrl" | "fetch">,
  endpoint: string,
  timeoutMs: number,
): Promise<ILinkResult<Record<string, unknown>>> {
  const fetchImpl = config.fetch ?? fetch
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const res = await fetchImpl(joinUrl(config.baseUrl, endpoint), {
      method: "GET",
      headers: buildIlinkGetHeaders(),
      signal: ctrl.signal,
    })
    return await readJson(res)
  } catch (err: unknown) {
    const name = err instanceof Error ? err.name : ""
    if (name === "AbortError" || name === "TimeoutError") {
      return { ok: false, reason: "timeout" }
    }
    return { ok: false, reason: err instanceof Error ? err.message : String(err) }
  } finally {
    clearTimeout(timer)
  }
}

export async function ilinkGetBotQr(
  config: Pick<ILinkClientConfig, "baseUrl" | "fetch">,
  botType = "3",
): Promise<ILinkResult<Record<string, unknown>>> {
  return ilinkGet(config, `${EP_GET_BOT_QR}?bot_type=${encodeURIComponent(botType)}`, 35_000)
}

export async function ilinkGetQrStatus(
  config: Pick<ILinkClientConfig, "baseUrl" | "fetch">,
  qrcode: string,
): Promise<ILinkResult<Record<string, unknown>>> {
  return ilinkGet(config, `${EP_GET_QR_STATUS}?qrcode=${encodeURIComponent(qrcode)}`, 35_000)
}

export type QrStatusAction =
  | { readonly kind: "wait" }
  | { readonly kind: "scaned" }
  | { readonly kind: "expired" }
  | { readonly kind: "redirect"; readonly host: string }
  | {
      readonly kind: "confirmed"
      readonly accountId: string
      readonly token: string
      readonly baseUrl: string
      readonly userId: string
    }

export function interpretQrStatus(response: Record<string, unknown>): QrStatusAction {
  const status = String(response["status"] ?? "wait")
  if (status === "scaned_but_redirect") {
    return { kind: "redirect", host: String(response["redirect_host"] ?? "") }
  }
  if (status === "expired") return { kind: "expired" }
  if (status === "scaned") return { kind: "scaned" }
  if (status === "confirmed") {
    return {
      kind: "confirmed",
      accountId: String(response["ilink_bot_id"] ?? ""),
      token: String(response["bot_token"] ?? ""),
      baseUrl: String(response["baseurl"] ?? ""),
      userId: String(response["ilink_user_id"] ?? ""),
    }
  }
  return { kind: "wait" }
}

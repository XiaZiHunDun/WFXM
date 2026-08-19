import {
  buildGetUpdatesBody,
  buildIlinkHeaders,
  buildSendMessageBody,
  EP_GET_UPDATES,
  EP_SEND_MESSAGE,
  type ILinkResult,
} from "./ilink-protocol.js"

export {
  buildGetUpdatesBody,
  buildIlinkHeaders,
  buildSendMessageBody,
  CHANNEL_VERSION,
  DEFAULT_ILINK_BASE_URL,
  EP_GET_UPDATES,
  EP_SEND_MESSAGE,
  extractIlinkText,
  ILINK_APP_CLIENT_VERSION,
  ILINK_APP_ID,
  inboundFromIlinkMsg,
  isIlinkOk,
  isSessionExpired,
  ITEM_TEXT,
  MSG_STATE_FINISH,
  MSG_TYPE_BOT,
  SESSION_EXPIRED_ERRCODE,
} from "./ilink-protocol.js"
export type { ILinkResult, IlinkInbound } from "./ilink-protocol.js"

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

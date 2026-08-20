/**
 * Tencent iLink Bot API surface used by v4 `wechat_ilink` and
 * `openclaw-mock.mjs`. This is the long-poll bot protocol
 * (`/ilink/bot/getupdates` + `/ilink/bot/sendmessage`), not the
 * public Official Account `cgi-bin` API.
 */

export const DEFAULT_ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
export const ILINK_APP_ID = "bot"
export const CHANNEL_VERSION = "2.2.0"
export const ILINK_APP_CLIENT_VERSION = (2 << 16) | (2 << 8) | 0

export const EP_GET_UPDATES = "ilink/bot/getupdates"
export const EP_SEND_MESSAGE = "ilink/bot/sendmessage"
export const EP_GET_UPLOAD_URL = "ilink/bot/getuploadurl"
export const EP_GET_BOT_QR = "ilink/bot/get_bot_qrcode"
export const EP_GET_QR_STATUS = "ilink/bot/get_qrcode_status"

/** getuploadurl `media_type` (not the same as item_list type). */
export const MEDIA_TYPE_IMAGE = 1
export const MEDIA_TYPE_FILE = 3

export const ITEM_TEXT = 1
export const ITEM_IMAGE = 2
export const ITEM_VOICE = 3
export const ITEM_FILE = 4
export const ITEM_VIDEO = 5
export const MSG_TYPE_BOT = 2
export const MSG_STATE_FINISH = 2
export const SESSION_EXPIRED_ERRCODE = -14

export type ILinkResult<T> =
  { readonly ok: true; readonly value: T } | { readonly ok: false; readonly reason: string }

export type IlinkInbound = {
  readonly fromUserId: string
  readonly content: string
  readonly messageId: string
  readonly contextToken: string
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return undefined
  }
  return value as Record<string, unknown>
}

function strField(rec: Record<string, unknown>, key: string): string {
  const v = rec[key]
  return typeof v === "string" ? v : typeof v === "number" ? String(v) : ""
}

export function extractIlinkText(itemList: unknown): string {
  if (!Array.isArray(itemList)) {
    return ""
  }
  for (const raw of itemList) {
    const item = asRecord(raw)
    if (!item) continue
    const type = item["type"]
    if (type !== ITEM_TEXT && type !== "text") continue
    const textItem = asRecord(item["text_item"])
    if (!textItem) continue
    const text = strField(textItem, "text") || strField(textItem, "content")
    if (text.trim()) {
      return text
    }
  }
  return ""
}

function itemType(item: Record<string, unknown>): string | number | undefined {
  const type = item["type"]
  return typeof type === "string" || typeof type === "number" ? type : undefined
}

export function extractIlinkMediaPlaceholder(itemList: unknown): string {
  if (!Array.isArray(itemList)) {
    return ""
  }
  for (const raw of itemList) {
    const item = asRecord(raw)
    if (!item) continue
    const type = itemType(item)
    if (type === ITEM_IMAGE || type === "image") return "[收到图片，当前版本暂不解析媒体]"
    if (type === ITEM_VOICE || type === "voice") return "[收到语音，当前版本暂不解析媒体]"
    if (type === ITEM_VIDEO || type === "video") return "[收到视频，当前版本暂不解析媒体]"
    if (type === ITEM_FILE || type === "file") return "[收到文件，当前版本暂不解析媒体]"
  }
  return ""
}

export function extractIlinkVoiceText(itemList: unknown): string {
  if (!Array.isArray(itemList)) {
    return ""
  }
  for (const raw of itemList) {
    const item = asRecord(raw)
    if (!item) continue
    const type = itemType(item)
    if (type !== ITEM_VOICE && type !== "voice") continue
    const voiceItem = asRecord(item["voice_item"])
    if (!voiceItem) continue
    const text = strField(voiceItem, "text") || strField(voiceItem, "content")
    if (text.trim()) return text.trim()
  }
  return ""
}

export function extractIlinkContent(itemList: unknown): string {
  return (
    extractIlinkText(itemList) ||
    extractIlinkVoiceText(itemList) ||
    extractIlinkMediaPlaceholder(itemList)
  )
}

export function isIlinkGroupMessage(msg: unknown): boolean {
  const rec = asRecord(msg)
  if (!rec) return false
  return Boolean(strField(rec, "room_id").trim() || strField(rec, "chat_room_id").trim())
}

export function inboundFromIlinkMsg(msg: unknown): IlinkInbound | undefined {
  const rec = asRecord(msg)
  if (!rec) {
    return undefined
  }
  const fromUserId = strField(rec, "from_user_id").trim()
  if (!fromUserId) {
    return undefined
  }
  const content = extractIlinkContent(rec["item_list"])
  if (!content) {
    return undefined
  }
  const messageId =
    strField(rec, "message_id").trim() ||
    strField(rec, "msg_id").trim() ||
    strField(rec, "client_id").trim()
  const contextToken = strField(rec, "context_token").trim()
  return { fromUserId, content, messageId, contextToken }
}

export function isSessionExpired(response: Record<string, unknown>): boolean {
  const ret = response["ret"]
  const errcode = response["errcode"]
  return ret === SESSION_EXPIRED_ERRCODE || errcode === SESSION_EXPIRED_ERRCODE
}

export function isIlinkOk(response: Record<string, unknown>): boolean {
  const ret = response["ret"]
  const errcode = response["errcode"]
  const retOk = ret === 0 || ret === undefined || ret === null
  const errOk = errcode === 0 || errcode === undefined || errcode === null
  return retOk && errOk
}

export function buildIlinkHeaders(token: string): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    AuthorizationType: "ilink_bot_token",
    "iLink-App-Id": ILINK_APP_ID,
    "iLink-App-ClientVersion": String(ILINK_APP_CLIENT_VERSION),
    "X-WECHAT-UIN": String(Math.floor(Math.random() * 1_000_000_000)),
  }
  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }
  return headers
}

export function buildGetUpdatesBody(syncBuf: string): string {
  return JSON.stringify({
    get_updates_buf: syncBuf,
    base_info: { channel_version: CHANNEL_VERSION },
  })
}

export function buildSendMessageBody(input: {
  readonly to: string
  readonly text: string
  readonly clientId: string
  readonly contextToken?: string
}): string {
  const message: Record<string, unknown> = {
    from_user_id: "",
    to_user_id: input.to,
    client_id: input.clientId,
    message_type: MSG_TYPE_BOT,
    message_state: MSG_STATE_FINISH,
    item_list: [{ type: ITEM_TEXT, text_item: { text: input.text } }],
  }
  if (input.contextToken) {
    message["context_token"] = input.contextToken
  }
  return JSON.stringify({
    msg: message,
    base_info: { channel_version: CHANNEL_VERSION },
  })
}

const IMAGE_EXTENSIONS = new Set([".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"])

export function classifyOutboundMedia(fileName: string): "image" | "file" {
  const base = fileName.trim().toLowerCase()
  const dot = base.lastIndexOf(".")
  if (dot < 0) return "file"
  const ext = base.slice(dot)
  if (ext.includes("/") || ext.includes("..")) return "file"
  return IMAGE_EXTENSIONS.has(ext) ? "image" : "file"
}

export function cdnUploadUrl(cdnBaseUrl: string, uploadParam: string, filekey: string): string {
  const base = cdnBaseUrl.replace(/\/+$/, "")
  return `${base}/upload?encrypted_query_param=${encodeURIComponent(uploadParam)}&filekey=${encodeURIComponent(filekey)}`
}

export function buildGetUploadUrlBody(input: {
  readonly filekey: string
  readonly mediaType: number
  readonly toUserId: string
  readonly rawsize: number
  readonly rawfilemd5: string
  readonly filesize: number
  readonly aeskeyHex: string
}): string {
  return JSON.stringify({
    filekey: input.filekey,
    media_type: input.mediaType,
    to_user_id: input.toUserId,
    rawsize: input.rawsize,
    rawfilemd5: input.rawfilemd5,
    filesize: input.filesize,
    no_need_thumb: true,
    aeskey: input.aeskeyHex,
    base_info: { channel_version: CHANNEL_VERSION },
  })
}

export function buildSendMediaMessageBody(input: {
  readonly to: string
  readonly clientId: string
  readonly item: Record<string, unknown>
  readonly contextToken?: string
}): string {
  const message: Record<string, unknown> = {
    from_user_id: "",
    to_user_id: input.to,
    client_id: input.clientId,
    message_type: MSG_TYPE_BOT,
    message_state: MSG_STATE_FINISH,
    item_list: [input.item],
  }
  if (input.contextToken) {
    message["context_token"] = input.contextToken
  }
  return JSON.stringify({
    msg: message,
    base_info: { channel_version: CHANNEL_VERSION },
  })
}

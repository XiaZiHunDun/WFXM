/**
 * R8.x.21 — outbound WeChat image/file: getuploadurl + AES-128-ECB + CDN POST
 * + sendmessage item_list type=2/4.
 *
 * Failures return `{ ok: false }` — no throw. CDN hosts must pass the
 * same allowlist as inbound downloads.
 */
import { createHash, randomBytes } from "node:crypto"
import { ilinkPost, ilinkSendMessage, type ILinkClientConfig } from "./ilink.js"
import { aes128EcbEncrypt, aesKeyForApi, aesPaddedSize } from "./ilink-media-crypto.js"
import { assertWechatCdnUrl } from "./ilink-media.js"
import {
  buildGetUploadUrlBody,
  buildSendMediaMessageBody,
  cdnUploadUrl,
  classifyOutboundMedia,
  EP_GET_UPLOAD_URL,
  EP_SEND_MESSAGE,
  ITEM_FILE,
  ITEM_IMAGE,
  isIlinkOk,
  MEDIA_TYPE_FILE,
  MEDIA_TYPE_IMAGE,
  type ILinkResult,
} from "./ilink-protocol.js"

export type SendOutboundMediaInput = {
  readonly to: string
  readonly fileName: string
  readonly plaintext: Buffer
  readonly caption?: string
  readonly contextToken?: string
  readonly cdnBaseUrl: string
  readonly maxBytes: number
}

export type SendOutboundMediaValue = {
  readonly clientId: string
  readonly kind: "image" | "file"
}

function strField(rec: Record<string, unknown>, key: string): string {
  const v = rec[key]
  return typeof v === "string" ? v : typeof v === "number" ? String(v) : ""
}

function buildMediaItem(input: {
  readonly kind: "image" | "file"
  readonly fileName: string
  readonly encryptQueryParam: string
  readonly aesKey: Buffer
  readonly ciphertextSize: number
  readonly plaintextSize: number
}): Record<string, unknown> {
  const media = {
    encrypt_query_param: input.encryptQueryParam,
    aes_key: aesKeyForApi(input.aesKey),
    encrypt_type: 1,
  }
  if (input.kind === "image") {
    return {
      type: ITEM_IMAGE,
      image_item: { media, mid_size: input.ciphertextSize },
    }
  }
  return {
    type: ITEM_FILE,
    file_item: {
      media,
      file_name: input.fileName,
      len: String(input.plaintextSize),
    },
  }
}

async function postCiphertext(
  config: ILinkClientConfig,
  uploadUrl: string,
  ciphertext: Buffer,
): Promise<ILinkResult<string>> {
  const fetchImpl = config.fetch ?? fetch
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 120_000)
  try {
    const res = await fetchImpl(uploadUrl, {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: new Uint8Array(ciphertext),
      signal: ctrl.signal,
    })
    if (!res.ok) {
      const raw = await res.text()
      return { ok: false, reason: `CDN upload HTTP ${res.status}: ${raw.slice(0, 200)}` }
    }
    const encrypted = res.headers.get("x-encrypted-param")?.trim() ?? ""
    await res.arrayBuffer()
    if (!encrypted) return { ok: false, reason: "CDN upload missing x-encrypted-param header" }
    return { ok: true, value: encrypted }
  } catch (err: unknown) {
    const name = err instanceof Error ? err.name : ""
    if (name === "AbortError" || name === "TimeoutError") {
      return { ok: false, reason: "CDN upload timeout" }
    }
    return { ok: false, reason: err instanceof Error ? err.message : String(err) }
  } finally {
    clearTimeout(timer)
  }
}

function resolveUploadUrl(
  response: Record<string, unknown>,
  cdnBaseUrl: string,
  filekey: string,
): ILinkResult<string> {
  const full = strField(response, "upload_full_url").trim()
  if (full) return { ok: true, value: full }
  const param = strField(response, "upload_param").trim()
  if (param) return { ok: true, value: cdnUploadUrl(cdnBaseUrl, param, filekey) }
  return { ok: false, reason: "getuploadurl returned no upload URL" }
}

export async function sendOutboundMedia(
  config: ILinkClientConfig,
  input: SendOutboundMediaInput,
): Promise<ILinkResult<SendOutboundMediaValue>> {
  const to = input.to.trim()
  if (!to) return { ok: false, reason: "recipient is required" }
  const fileName = input.fileName.trim()
  if (!fileName) return { ok: false, reason: "file name is required" }
  if (input.plaintext.length === 0) return { ok: false, reason: "file is empty" }
  if (input.plaintext.length > input.maxBytes) {
    return { ok: false, reason: `file exceeds ${input.maxBytes} bytes` }
  }

  const kind = classifyOutboundMedia(fileName)
  const mediaType = kind === "image" ? MEDIA_TYPE_IMAGE : MEDIA_TYPE_FILE
  const filekey = randomBytes(16).toString("hex")
  const aesKey = randomBytes(16)
  const rawfilemd5 = createHash("md5").update(input.plaintext).digest("hex")
  const filesize = aesPaddedSize(input.plaintext.length)

  const urlResult = await ilinkPost(
    config,
    EP_GET_UPLOAD_URL,
    buildGetUploadUrlBody({
      filekey,
      mediaType,
      toUserId: to,
      rawsize: input.plaintext.length,
      rawfilemd5,
      filesize,
      aeskeyHex: aesKey.toString("hex"),
    }),
    15_000,
  )
  if (!urlResult.ok) return urlResult
  if (!isIlinkOk(urlResult.value)) {
    return { ok: false, reason: `getuploadurl ret=${String(urlResult.value["ret"] ?? "unknown")}` }
  }

  const uploadUrl = resolveUploadUrl(urlResult.value, input.cdnBaseUrl, filekey)
  if (!uploadUrl.ok) return uploadUrl
  const allowed = assertWechatCdnUrl(uploadUrl.value)
  if (!allowed.ok) return allowed

  const encrypted = aes128EcbEncrypt(input.plaintext, aesKey)
  if (!encrypted.ok) return encrypted

  const eqp = await postCiphertext(config, uploadUrl.value, encrypted.value)
  if (!eqp.ok) return eqp

  const caption = input.caption?.trim() ?? ""
  if (caption) {
    const captionSend = await ilinkSendMessage(config, {
      to,
      text: caption,
      ...(input.contextToken ? { contextToken: input.contextToken } : {}),
    })
    if (!captionSend.ok) return captionSend
  }

  const clientId = `v5-media-${Date.now()}`
  const sendBody = buildSendMediaMessageBody({
    to,
    clientId,
    item: buildMediaItem({
      kind,
      fileName,
      encryptQueryParam: eqp.value,
      aesKey,
      ciphertextSize: encrypted.value.length,
      plaintextSize: input.plaintext.length,
    }),
    ...(input.contextToken ? { contextToken: input.contextToken } : {}),
  })
  const sent = await ilinkPost(config, EP_SEND_MESSAGE, sendBody, 15_000)
  if (!sent.ok) return sent
  if (!isIlinkOk(sent.value)) {
    return { ok: false, reason: `sendmessage ret=${String(sent.value["ret"] ?? "unknown")}` }
  }
  return { ok: true, value: { clientId, kind } }
}

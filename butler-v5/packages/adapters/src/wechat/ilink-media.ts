import { mkdirSync, writeFileSync } from "node:fs"
import { basename, join } from "node:path"
import { aes128EcbDecrypt, parseAesKey } from "./ilink-media-crypto.js"
import {
  ITEM_FILE,
  ITEM_IMAGE,
  ITEM_VIDEO,
  ITEM_VOICE,
  extractIlinkVoiceText,
  type ILinkResult,
} from "./ilink-protocol.js"

export { WECHAT_OUTBOUND_NETWORK_HOSTS } from "@butler/domain/governance/wechat-network-hosts.js"
import { WECHAT_OUTBOUND_NETWORK_HOST_SET } from "@butler/domain/governance/wechat-network-hosts.js"

export const DEFAULT_WECHAT_CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"

const WECHAT_CDN_HOSTS = WECHAT_OUTBOUND_NETWORK_HOST_SET

export type IlinkMediaKind = "image" | "voice" | "file" | "video"

export type IlinkMediaRef = {
  readonly kind: IlinkMediaKind
  readonly encryptQueryParam?: string
  readonly fullUrl?: string
  readonly aesKeyB64?: string
  readonly fileName?: string
}

export type IlinkMediaDownloadConfig = {
  readonly cacheDir: string
  readonly cdnBaseUrl: string
  readonly fetch: typeof fetch
  readonly maxBytes: number
  readonly timeoutMs?: number
  readonly transcribeVoice?: (path: string) => Promise<ILinkResult<string>>
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

function itemKind(type: unknown): IlinkMediaKind | undefined {
  if (type === ITEM_IMAGE || type === "image") return "image"
  if (type === ITEM_VOICE || type === "voice") return "voice"
  if (type === ITEM_VIDEO || type === "video") return "video"
  if (type === ITEM_FILE || type === "file") return "file"
  return undefined
}

function nestedKey(kind: IlinkMediaKind): string {
  if (kind === "image") return "image_item"
  if (kind === "voice") return "voice_item"
  if (kind === "video") return "video_item"
  return "file_item"
}

function aesKeyFromItem(nested: Record<string, unknown>, media: Record<string, unknown>): string {
  const hex = strField(nested, "aeskey")
  if (/^[0-9a-fA-F]{32}$/.test(hex)) {
    return Buffer.from(hex, "hex").toString("base64")
  }
  return strField(media, "aes_key") || strField(nested, "aes_key")
}

export function extractIlinkMediaRef(itemList: unknown): IlinkMediaRef | undefined {
  if (!Array.isArray(itemList)) return undefined
  for (const raw of itemList) {
    const item = asRecord(raw)
    if (!item) continue
    const kind = itemKind(item["type"])
    if (!kind) continue
    const nested = asRecord(item[nestedKey(kind)]) ?? {}
    const media = asRecord(nested["media"]) ?? {}
    const encryptQueryParam = strField(media, "encrypt_query_param").trim()
    const fullUrl = strField(media, "full_url").trim() || strField(nested, "url").trim()
    const aesKeyB64 = aesKeyFromItem(nested, media).trim()
    const fileName = strField(nested, "file_name").trim()
    const ref: IlinkMediaRef = {
      kind,
      ...(encryptQueryParam ? { encryptQueryParam } : {}),
      ...(fullUrl ? { fullUrl } : {}),
      ...(aesKeyB64 ? { aesKeyB64 } : {}),
      ...(fileName ? { fileName } : {}),
    }
    if (ref.encryptQueryParam || ref.fullUrl) return ref
  }
  return undefined
}

export function assertWechatCdnUrl(url: string): ILinkResult<URL> {
  let parsed: URL
  try {
    parsed = new URL(url)
  } catch {
    return { ok: false, reason: "unparseable media URL" }
  }
  const scheme = parsed.protocol.replace(":", "").toLowerCase()
  if (scheme !== "http" && scheme !== "https") {
    return { ok: false, reason: `disallowed media URL scheme ${scheme}` }
  }
  const host = parsed.hostname.toLowerCase()
  if (!WECHAT_CDN_HOSTS.has(host)) {
    return { ok: false, reason: `media URL host ${host} is not a WeChat CDN` }
  }
  return { ok: true, value: parsed }
}

export function cdnDownloadUrl(cdnBaseUrl: string, encryptedQueryParam: string): string {
  const base = cdnBaseUrl.replace(/\/+$/, "")
  return `${base}/download?encrypted_query_param=${encodeURIComponent(encryptedQueryParam)}`
}

function extensionFor(kind: IlinkMediaKind, fileName: string | undefined): string {
  if (fileName) {
    const base = basename(fileName)
    const dot = base.lastIndexOf(".")
    if (dot > 0 && !base.includes("..")) return base.slice(dot)
  }
  if (kind === "image") return ".jpg"
  if (kind === "voice") return ".silk"
  if (kind === "video") return ".mp4"
  return ".bin"
}

function safeFileName(kind: IlinkMediaKind, fileName: string | undefined): string {
  const ext = extensionFor(kind, fileName)
  return `${kind}-${crypto.randomUUID()}${ext}`
}

export function describeSavedMedia(kind: IlinkMediaKind, path: string): string {
  const label =
    kind === "image" ? "图片" : kind === "voice" ? "语音" : kind === "video" ? "视频" : "文件"
  return `收到${label}，已保存到 ${path}`
}

async function fetchBytes(
  url: string,
  fetchImpl: typeof fetch,
  maxBytes: number,
  timeoutMs: number,
): Promise<ILinkResult<Buffer>> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const res = await fetchImpl(url, { signal: ctrl.signal })
    if (!res.ok) return { ok: false, reason: `media HTTP ${res.status}` }
    const buf = Buffer.from(await res.arrayBuffer())
    if (buf.length > maxBytes) {
      return { ok: false, reason: `media exceeds ${maxBytes} bytes` }
    }
    return { ok: true, value: buf }
  } catch (err) {
    return { ok: false, reason: err instanceof Error ? err.message : String(err) }
  } finally {
    clearTimeout(timer)
  }
}

export async function downloadAndCacheIlinkMedia(
  ref: IlinkMediaRef,
  config: IlinkMediaDownloadConfig,
): Promise<ILinkResult<{ readonly path: string; readonly kind: IlinkMediaKind }>> {
  let url: string
  if (ref.encryptQueryParam) {
    url = cdnDownloadUrl(config.cdnBaseUrl, ref.encryptQueryParam)
    const allowed = assertWechatCdnUrl(url)
    if (!allowed.ok) return allowed
  } else if (ref.fullUrl) {
    const allowed = assertWechatCdnUrl(ref.fullUrl)
    if (!allowed.ok) return allowed
    url = ref.fullUrl
  } else {
    return { ok: false, reason: "media item had neither encrypt_query_param nor full_url" }
  }

  const timeoutMs = config.timeoutMs ?? 30_000
  const downloaded = await fetchBytes(url, config.fetch, config.maxBytes, timeoutMs)
  if (!downloaded.ok) return downloaded
  let bytes = downloaded.value
  if (ref.aesKeyB64) {
    const key = parseAesKey(ref.aesKeyB64)
    if (!key.ok) return key
    bytes = aes128EcbDecrypt(bytes, key.value)
  }
  try {
    mkdirSync(config.cacheDir, { recursive: true })
    const path = join(config.cacheDir, safeFileName(ref.kind, ref.fileName))
    writeFileSync(path, bytes)
    return { ok: true, value: { path, kind: ref.kind } }
  } catch (err) {
    return { ok: false, reason: err instanceof Error ? err.message : String(err) }
  }
}

export async function enrichIlinkInboundContent(
  itemList: unknown,
  existingContent: string,
  config: IlinkMediaDownloadConfig,
): Promise<string> {
  const voiceText = extractIlinkVoiceText(itemList)
  if (voiceText) return `收到语音：${voiceText}`

  const ref = extractIlinkMediaRef(itemList)
  if (!ref) return existingContent
  const saved = await downloadAndCacheIlinkMedia(ref, config)
  if (!saved.ok) return existingContent
  if (saved.value.kind === "voice" && config.transcribeVoice) {
    const asr = await config.transcribeVoice(saved.value.path)
    if (asr.ok) {
      return `收到语音转写：${asr.value}\n已保存到 ${saved.value.path}`
    }
  }
  const note = describeSavedMedia(saved.value.kind, saved.value.path)
  const placeholder = existingContent.includes("当前版本暂不解析媒体")
  if (!existingContent.trim() || placeholder) return note
  return `${existingContent}\n${note}`
}

import { readFile } from "node:fs/promises"
import { basename, isAbsolute, resolve } from "node:path"
import { access } from "node:fs/promises"

export type ChannelOutboundResult =
  | { readonly ok: true }
  | { readonly ok: false; readonly reason: string }

const MEDIA_TAG_RE = /\[\[media:([^\]]+)\]\]/g
const IMAGE_EXT = new Set([".png", ".jpg", ".jpeg", ".gif", ".webp"])

export interface ChannelOutboundAttachment {
  readonly path: string
  readonly kind: "image" | "file"
  readonly name: string
}

export interface ParsedChannelOutbound {
  readonly text: string
  readonly attachments: readonly ChannelOutboundAttachment[]
}

function envTruthy(raw: string | undefined): boolean {
  if (!raw) return false
  const text = raw.trim().toLowerCase()
  return text === "1" || text === "true" || text === "yes" || text === "on"
}

export function channelOutboundMediaEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return envTruthy(env["BUTLER_V5_CHANNEL_OUTBOUND_MEDIA"])
}

export function mediaKindForPath(filePath: string): "image" | "file" {
  const lower = filePath.toLowerCase()
  for (const ext of IMAGE_EXT) {
    if (lower.endsWith(ext)) return "image"
  }
  return "file"
}

export function parseChannelOutboundMedia(reply: string): ParsedChannelOutbound {
  const attachments: ChannelOutboundAttachment[] = []
  const seen = new Set<string>()
  for (const match of reply.matchAll(MEDIA_TAG_RE)) {
    const rawPath = match[1]?.trim()
    if (!rawPath || seen.has(rawPath)) continue
    seen.add(rawPath)
    attachments.push({
      path: rawPath,
      kind: mediaKindForPath(rawPath),
      name: basename(rawPath),
    })
  }
  const text = reply
    .replace(MEDIA_TAG_RE, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
  return { text, attachments }
}

export function allowedOutboundMediaRoots(env: NodeJS.ProcessEnv = process.env): readonly string[] {
  const roots = [resolve(process.cwd()), resolve(process.cwd(), ".butler-v5")]
  const workspace = (env["BUTLER_V5_WORKSPACE"] ?? "").trim()
  if (workspace) roots.push(resolve(workspace))
  const telegramDir = (env["BUTLER_V5_TELEGRAM_MEDIA_DIR"] ?? "").trim()
  if (telegramDir) roots.push(resolve(telegramDir))
  return roots
}

export function isAllowedOutboundMediaPath(
  filePath: string,
  env: NodeJS.ProcessEnv = process.env,
): boolean {
  const resolved = resolve(isAbsolute(filePath) ? filePath : resolve(process.cwd(), filePath))
  return allowedOutboundMediaRoots(env).some(
    (root) => resolved === root || resolved.startsWith(`${root}/`),
  )
}

export async function resolveOutboundAttachment(
  attachment: ChannelOutboundAttachment,
  env: NodeJS.ProcessEnv = process.env,
): Promise<
  | { readonly ok: true; readonly path: string; readonly bytes: Buffer }
  | { readonly ok: false; readonly reason: string }
> {
  if (!isAllowedOutboundMediaPath(attachment.path, env)) {
    return { ok: false, reason: `media path not allowed: ${attachment.path}` }
  }
  const resolved = resolve(
    isAbsolute(attachment.path) ? attachment.path : resolve(process.cwd(), attachment.path),
  )
  try {
    await access(resolved)
    const bytes = await readFile(resolved)
    return { ok: true, path: resolved, bytes }
  } catch {
    return { ok: false, reason: `media file missing: ${attachment.path}` }
  }
}

export async function sendSlackOutboundFile(config: {
  readonly token: string
  readonly channel: string
  readonly filePath: string
  readonly fileName: string
  readonly bytes: Buffer
  readonly comment?: string
  readonly threadTs?: string
  readonly fetch?: typeof fetch
  readonly timeoutMs?: number
}): Promise<ChannelOutboundResult> {
  const fetchFn = config.fetch ?? fetch
  const form = new FormData()
  form.append("channels", config.channel)
  form.append("filename", config.fileName)
  form.append("file", new Blob([new Uint8Array(config.bytes)]), config.fileName)
  if (config.comment?.trim()) form.append("initial_comment", config.comment.trim())
  if (config.threadTs) form.append("thread_ts", config.threadTs)

  const controller = new AbortController()
  const timeoutMs = config.timeoutMs ?? 30_000
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetchFn("https://slack.com/api/files.upload", {
      method: "POST",
      headers: { authorization: `Bearer ${config.token.trim()}` },
      body: form,
      signal: controller.signal,
    })
    const parsed = JSON.parse(await res.text()) as { readonly ok?: boolean; readonly error?: string }
    if (!res.ok || !parsed.ok) {
      return { ok: false, reason: parsed.error ?? `slack files.upload HTTP ${res.status}` }
    }
    return { ok: true }
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      return { ok: false, reason: `slack files.upload timeout after ${timeoutMs}ms` }
    }
    return { ok: false, reason: err instanceof Error ? err.message : String(err) }
  } finally {
    clearTimeout(timer)
  }
}

export async function sendTelegramOutboundMedia(config: {
  readonly token: string
  readonly chatId: string
  readonly attachment: ChannelOutboundAttachment
  readonly bytes: Buffer
  readonly caption?: string
  readonly fetch?: typeof fetch
  readonly timeoutMs?: number
}): Promise<ChannelOutboundResult> {
  const fetchFn = config.fetch ?? fetch
  const token = config.token.trim()
  const method = config.attachment.kind === "image" ? "sendPhoto" : "sendDocument"
  const field = config.attachment.kind === "image" ? "photo" : "document"
  const url = `https://api.telegram.org/bot${token}/${method}`
  const form = new FormData()
  form.append("chat_id", config.chatId)
  form.append(field, new Blob([new Uint8Array(config.bytes)]), config.attachment.name)
  if (config.caption?.trim()) form.append("caption", config.caption.trim().slice(0, 1024))

  const controller = new AbortController()
  const timeoutMs = config.timeoutMs ?? 30_000
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetchFn(url, { method: "POST", body: form, signal: controller.signal })
    const parsed = JSON.parse(await res.text()) as {
      readonly ok?: boolean
      readonly description?: string
    }
    if (!res.ok || !parsed.ok) {
      return { ok: false, reason: parsed.description ?? `telegram ${method} HTTP ${res.status}` }
    }
    return { ok: true }
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      return { ok: false, reason: `telegram ${method} timeout after ${timeoutMs}ms` }
    }
    return { ok: false, reason: err instanceof Error ? err.message : String(err) }
  } finally {
    clearTimeout(timer)
  }
}

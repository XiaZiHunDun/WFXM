import { mkdir, writeFile } from "node:fs/promises"
import { join } from "node:path"

export type ChannelMediaKind = "image" | "file" | "audio" | "video"

export interface ChannelInboundMedia {
  readonly kind: ChannelMediaKind
  readonly name?: string
  readonly mimeType?: string
  readonly fileId?: string
  readonly url?: string
  readonly sizeBytes?: number
  readonly localPath?: string
}

export interface ChannelMediaContent {
  readonly content: string
  readonly media: readonly ChannelInboundMedia[]
}

function envTruthy(raw: string | undefined): boolean {
  if (!raw) return false
  const text = raw.trim().toLowerCase()
  return text === "1" || text === "true" || text === "yes" || text === "on"
}

export function telegramMediaCacheEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return envTruthy(env["BUTLER_V5_TELEGRAM_MEDIA_CACHE"])
}

export function telegramMediaCacheDir(env: NodeJS.ProcessEnv = process.env): string {
  const custom = (env["BUTLER_V5_TELEGRAM_MEDIA_DIR"] ?? "").trim()
  if (custom) return custom
  return join(process.cwd(), ".butler-v5", "telegram-media")
}

function slackMediaKind(mimeType: string): ChannelMediaKind {
  if (mimeType.startsWith("image/")) return "image"
  if (mimeType.startsWith("audio/")) return "audio"
  if (mimeType.startsWith("video/")) return "video"
  return "file"
}

export function describeSlackFiles(
  files: unknown,
  textFallback = "",
): ChannelMediaContent | null {
  if (!Array.isArray(files) || files.length === 0) return null
  const media: ChannelInboundMedia[] = []
  const lines: string[] = []
  for (const entry of files) {
    if (!entry || typeof entry !== "object") continue
    const rec = entry as Record<string, unknown>
    const name = typeof rec["name"] === "string" ? rec["name"].trim() : "attachment"
    const mimeType = typeof rec["mimetype"] === "string" ? rec["mimetype"] : "application/octet-stream"
    const url = typeof rec["url_private"] === "string" ? rec["url_private"] : undefined
    const sizeBytes = typeof rec["size"] === "number" ? rec["size"] : undefined
    const kind = slackMediaKind(mimeType)
    media.push({
      kind,
      name,
      mimeType,
      ...(url ? { url } : {}),
      ...(sizeBytes !== undefined ? { sizeBytes } : {}),
    })
    lines.push(`[slack ${kind} name=${name} mimetype=${mimeType}]`)
  }
  if (media.length === 0) return null
  const caption = textFallback.trim()
  const content = caption
    ? `${caption}\n${lines.join("\n")}`
    : lines.join("\n")
  return { content, media }
}

export function describeTelegramMedia(msg: Record<string, unknown>): ChannelMediaContent | null {
  const caption = typeof msg["caption"] === "string" ? msg["caption"].trim() : ""
  const text = typeof msg["text"] === "string" ? msg["text"].trim() : ""

  const photo = msg["photo"]
  if (Array.isArray(photo) && photo.length > 0) {
    const largest = photo[photo.length - 1]
    if (largest && typeof largest === "object") {
      const rec = largest as Record<string, unknown>
      const fileId = typeof rec["file_id"] === "string" ? rec["file_id"] : undefined
      const sizeBytes = typeof rec["file_size"] === "number" ? rec["file_size"] : undefined
      if (fileId) {
        const line = `[telegram image file_id=${fileId}]`
        return {
          content: caption || text || line,
          media: [
            {
              kind: "image",
              fileId,
              mimeType: "image/jpeg",
              ...(sizeBytes !== undefined ? { sizeBytes } : {}),
            },
          ],
        }
      }
    }
  }

  const document = msg["document"]
  if (document && typeof document === "object") {
    const rec = document as Record<string, unknown>
    const fileId = typeof rec["file_id"] === "string" ? rec["file_id"] : undefined
    const name = typeof rec["file_name"] === "string" ? rec["file_name"] : "document"
    const mimeType =
      typeof rec["mime_type"] === "string" ? rec["mime_type"] : "application/octet-stream"
    const sizeBytes = typeof rec["file_size"] === "number" ? rec["file_size"] : undefined
    if (fileId) {
      const line = `[telegram file name=${name} file_id=${fileId}]`
      return {
        content: caption || text || line,
        media: [
          {
            kind: "file",
            name,
            fileId,
            mimeType,
            ...(sizeBytes !== undefined ? { sizeBytes } : {}),
          },
        ],
      }
    }
  }

  return null
}

export async function enrichTelegramMediaContent(
  base: ChannelMediaContent,
  config: {
    readonly token: string
    readonly cacheDir: string
    readonly maxBytes: number
    readonly fetch?: typeof fetch
  },
): Promise<ChannelMediaContent> {
  const token = config.token.trim()
  if (!token) return base
  const fetchFn = config.fetch ?? fetch
  const enriched: ChannelInboundMedia[] = []
  const extraLines: string[] = []

  for (const item of base.media) {
    if (!item.fileId) {
      enriched.push(item)
      continue
    }
    const cached = await downloadTelegramFile({
      token,
      fileId: item.fileId,
      cacheDir: config.cacheDir,
      maxBytes: config.maxBytes,
      fetch: fetchFn,
      suggestedName: item.name ?? `${item.fileId}.bin`,
    })
    if (cached.ok) {
      enriched.push({ ...item, localPath: cached.path })
      extraLines.push(`saved to ${cached.path}`)
    } else {
      enriched.push(item)
      extraLines.push(`download failed: ${cached.reason}`)
    }
  }

  if (extraLines.length === 0) return { ...base, media: enriched }
  return {
    content: `${base.content}\n${extraLines.join("\n")}`,
    media: enriched,
  }
}

export async function downloadTelegramFile(config: {
  readonly token: string
  readonly fileId: string
  readonly cacheDir: string
  readonly maxBytes: number
  readonly suggestedName: string
  readonly fetch?: typeof fetch
}): Promise<{ readonly ok: true; readonly path: string } | { readonly ok: false; readonly reason: string }> {
  const fetchFn = config.fetch ?? fetch
  const getFileUrl = `https://api.telegram.org/bot${config.token}/getFile?file_id=${encodeURIComponent(config.fileId)}`
  try {
    const metaRes = await fetchFn(getFileUrl)
    const metaRaw = await metaRes.text()
    const meta = JSON.parse(metaRaw) as {
      readonly ok?: boolean
      readonly result?: { readonly file_path?: string; readonly file_size?: number }
    }
    if (!metaRes.ok || !meta.ok || !meta.result?.file_path) {
      return { ok: false, reason: "telegram getFile failed" }
    }
    if (meta.result.file_size !== undefined && meta.result.file_size > config.maxBytes) {
      return { ok: false, reason: `telegram file exceeds ${config.maxBytes} bytes` }
    }
    const fileUrl = `https://api.telegram.org/file/bot${config.token}/${meta.result.file_path}`
    const fileRes = await fetchFn(fileUrl)
    if (!fileRes.ok) {
      return { ok: false, reason: `telegram file HTTP ${fileRes.status}` }
    }
    const buf = Buffer.from(await fileRes.arrayBuffer())
    if (buf.length > config.maxBytes) {
      return { ok: false, reason: `telegram file exceeds ${config.maxBytes} bytes` }
    }
    await mkdir(config.cacheDir, { recursive: true })
    const safeName = config.suggestedName.replace(/[^\w.-]+/g, "_").slice(0, 120)
    const path = join(config.cacheDir, `${config.fileId}-${safeName}`)
    await writeFile(path, buf)
    return { ok: true, path }
  } catch (err) {
    return { ok: false, reason: err instanceof Error ? err.message : String(err) }
  }
}

export function telegramMediaMaxBytes(env: NodeJS.ProcessEnv = process.env): number {
  const raw = Number(env["BUTLER_V5_TELEGRAM_MEDIA_MAX_BYTES"] ?? 8 * 1024 * 1024)
  return Number.isFinite(raw) && raw > 0 ? raw : 8 * 1024 * 1024
}

export async function resolveTelegramInboundContent(
  parsed: { readonly content: string; readonly media?: readonly ChannelInboundMedia[] },
  env: NodeJS.ProcessEnv = process.env,
  options: { readonly fetch?: typeof fetch } = {},
): Promise<string> {
  if (!parsed.media?.length || !telegramMediaCacheEnabled(env)) {
    return parsed.content
  }
  const token = (env["BUTLER_V5_TELEGRAM_BOT_TOKEN"] ?? "").trim()
  if (!token) return parsed.content
  const enriched = await enrichTelegramMediaContent(
    { content: parsed.content, media: parsed.media },
    {
      token,
      cacheDir: telegramMediaCacheDir(env),
      maxBytes: telegramMediaMaxBytes(env),
      ...(options.fetch ? { fetch: options.fetch } : {}),
    },
  )
  return enriched.content
}

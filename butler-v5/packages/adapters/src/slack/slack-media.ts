/**
 * Slack inbound media classification (file_share subtype handling).
 *
 * Returns a ChannelMediaContent (caption + media list) or null when
 * no usable file metadata exists. Pure parser, no I/O.
 *
 * NOTE: ChannelMediaKind / ChannelInboundMedia / ChannelMediaContent are
 * shared structural types used by both Slack (here) and Telegram
 * (`apps/api/src/channel-media.ts` describeTelegramMedia + helpers).
 * When Telegram adapter is extracted (future ADR), these types should
 * move to a shared location. For now Slack is the source of truth —
 * apps/api imports them back via `@butler/adapters/slack`.
 */

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
    const name = (typeof rec["name"] === "string" ? rec["name"].trim() : "") || "attachment"
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
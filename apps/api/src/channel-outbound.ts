import {
  channelOutboundMediaEnabled,
  parseChannelOutboundMedia,
  resolveOutboundAttachment,
  sendTelegramOutboundMedia,
} from "./channel-outbound-media.js"
import { sendSlackOutboundFile, sendSlackOutboundMessage } from "@butler/adapters/slack/index.js"
import { DEFAULT_TELEGRAM_TEXT_TIMEOUT_MS } from "@butler/adapters"
import { finalizeReply, splitForWechat } from "@butler/runtime/butler/presentation.js"
import { Secret } from "@butler/adapters/wechat/secret.js"
import { mapChannelErrorToOwnerJargon } from "./owner-jargon.js"

export type ChannelOutboundResult =
  { readonly ok: true } | { readonly ok: false; readonly reason: string }

export interface TelegramOutboundConfig {
  readonly token: string
  readonly chatId: string
  readonly text: string
  readonly fetch?: typeof fetch
  readonly timeoutMs?: number
}

const TELEGRAM_API = "https://api.telegram.org"
/** Conservative text budget shared by Slack and Telegram delivery. */
const CHANNEL_TEXT_LIMIT = 3900
/** Telegram captions are much shorter than message text. */
const TELEGRAM_CAPTION_LIMIT = 1024

function clipOutboundText(text: string, maxChars: number): string {
  const trimmed = text.trim()
  if (trimmed.length <= maxChars) return trimmed
  return `${trimmed.slice(0, Math.max(0, maxChars - 1))}…`
}

/**
 * Sends pre-split parts in order and reports which part failed. The caller
 * keeps ownership of wording; this helper only guarantees no silent drop.
 */
async function sendTextParts(
  parts: readonly string[],
  send: (text: string) => Promise<ChannelOutboundResult>,
): Promise<{ readonly ok: boolean; readonly reason?: string }> {
  for (const [index, part] of parts.entries()) {
    const result = await send(part)
    if (!result.ok) {
      return {
        ok: false,
        reason:
          parts.length > 1
            ? `${result.reason}（第 ${index + 1}/${parts.length} 段）`
            : result.reason,
      }
    }
  }
  return { ok: true }
}

function cleanedText(text: string): string {
  return text.trim().length === 0 ? "" : finalizeReply(text)
}

export async function sendTelegramOutboundMessage(
  config: TelegramOutboundConfig,
): Promise<ChannelOutboundResult> {
  const token = config.token.trim()
  if (!token) return { ok: false, reason: "缺少 Telegram bot token" }
  const chatId = config.chatId.trim()
  if (!chatId) return { ok: false, reason: "缺少 Telegram chat_id" }
  const text = clipOutboundText(config.text, 3900)
  if (!text) return { ok: false, reason: "回复内容为空" }

  const fetchFn = config.fetch ?? fetch
  const controller = new AbortController()
  const timeoutMs = config.timeoutMs ?? DEFAULT_TELEGRAM_TEXT_TIMEOUT_MS
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  const url = `${TELEGRAM_API}/bot${token}/sendMessage`
  try {
    const res = await fetchFn(url, {
      method: "POST",
      headers: { "content-type": "application/json; charset=utf-8" },
      body: JSON.stringify({ chat_id: chatId, text }),
      signal: controller.signal,
    })
    const raw = await res.text()
    // D69 T2 (audit #10 F-29): defensive parse — previous `as typeof parsed`
    // cast crashed on telegram 4xx returning null/array/scalar. Parse as
    // unknown first, then narrow.
    let parsed: unknown
    try {
      parsed = JSON.parse(raw)
    } catch {
      return { ok: false, reason: `Telegram 返回内容不是 JSON：${raw.slice(0, 200)}` }
    }
    const parsedObj =
      parsed !== null && typeof parsed === "object"
        ? (parsed as { readonly ok?: unknown; readonly description?: unknown })
        : null
    const ok = parsedObj?.ok === true
    const description =
      typeof parsedObj?.description === "string" ? parsedObj.description : undefined
    if (!res.ok || !ok) {
      // D74 T1 (audit #20 SO-002 + SO-029): route upstream Telegram
      // description AND our own English fallback through
      // mapChannelErrorToOwnerJargon so owner delivery audit never sees
      // raw English. SO-029 specifically addresses the case where
      // upstream description (e.g. 'Bad Request: chat not found') used
      // to override our Chinese fallback — now both paths are mapped.
      return {
        ok: false,
        reason: mapChannelErrorToOwnerJargon(description ?? `telegram API HTTP ${res.status}`),
      }
    }
    return { ok: true }
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      return {
        ok: false,
        reason: mapChannelErrorToOwnerJargon(`telegram API timeout after ${timeoutMs}ms`),
      }
    }
    return {
      ok: false,
      reason: mapChannelErrorToOwnerJargon(err instanceof Error ? err.message : String(err)),
    }
  } finally {
    clearTimeout(timer)
  }
}

export type ChannelDeliveryResult = {
  readonly delivered: boolean
  readonly deliveryReason?: string
  readonly mediaCount: number
}

export async function deliverSlackChannelReply(config: {
  readonly token: string
  readonly channel: string
  readonly reply: string
  readonly threadTs?: string
  readonly env?: NodeJS.ProcessEnv
  readonly fetch?: typeof fetch
}): Promise<ChannelDeliveryResult> {
  const env = config.env ?? process.env
  if (config.reply.trim().length === 0) {
    return { delivered: false, mediaCount: 0, deliveryReason: "回复内容为空" }
  }
  const parsed = parseChannelOutboundMedia(config.reply)
  const text = cleanedText(parsed.text)
  const parts = text.length === 0 ? [] : splitForWechat(text, CHANNEL_TEXT_LIMIT)
  const useMedia = channelOutboundMediaEnabled(env) && parsed.attachments.length > 0

  const sendPart = (part: string): Promise<ChannelOutboundResult> =>
    sendSlackOutboundMessage({
      token: config.token,
      channel: config.channel,
      text: part,
      ...(config.threadTs ? { threadTs: config.threadTs } : {}),
      ...(config.fetch ? { fetch: config.fetch } : {}),
    })

  if (!useMedia) {
    const outcome = await sendTextParts(parts, sendPart)
    return {
      delivered: outcome.ok,
      mediaCount: 0,
      ...(outcome.reason === undefined ? {} : { deliveryReason: outcome.reason }),
    }
  }

  let mediaSent = 0
  const reasons: string[] = []
  for (const attachment of parsed.attachments) {
    const resolved = await resolveOutboundAttachment(attachment, env)
    if (!resolved.ok) {
      reasons.push(resolved.reason)
      continue
    }
    const upload = await sendSlackOutboundFile({
      token: config.token,
      channel: config.channel,
      filePath: resolved.path,
      fileName: attachment.name,
      bytes: resolved.bytes,
      ...(mediaSent === 0 && parts[0] ? { comment: parts[0] } : {}),
      ...(config.threadTs ? { threadTs: config.threadTs } : {}),
      ...(config.fetch ? { fetch: config.fetch } : {}),
    })
    if (upload.ok) mediaSent += 1
    else reasons.push(upload.reason)
  }
  // Any text the first attachment did not carry is still delivered separately.
  const remainder = mediaSent === 0 ? parts : parts.slice(1)
  const outcome = await sendTextParts(remainder, sendPart)
  const deliveryReason = [reasons.join("; "), outcome.reason].filter(
    (reason): reason is string => typeof reason === "string" && reason.length > 0,
  )
  return {
    delivered: outcome.ok && (mediaSent > 0 || parts.length > 0),
    mediaCount: mediaSent,
    ...(deliveryReason.length === 0 ? {} : { deliveryReason: deliveryReason.join("; ") }),
  }
}

export async function deliverTelegramChannelReply(config: {
  readonly token: string
  readonly chatId: string
  readonly reply: string
  readonly env?: NodeJS.ProcessEnv
  readonly fetch?: typeof fetch
}): Promise<ChannelDeliveryResult> {
  const env = config.env ?? process.env
  if (config.reply.trim().length === 0) {
    return { delivered: false, mediaCount: 0, deliveryReason: "回复内容为空" }
  }
  const parsed = parseChannelOutboundMedia(config.reply)
  const text = cleanedText(parsed.text)
  const parts = text.length === 0 ? [] : splitForWechat(text, CHANNEL_TEXT_LIMIT)
  const useMedia = channelOutboundMediaEnabled(env) && parsed.attachments.length > 0

  const sendPart = (part: string): Promise<ChannelOutboundResult> =>
    sendTelegramOutboundMessage({
      token: config.token,
      chatId: config.chatId,
      text: part,
      ...(config.fetch ? { fetch: config.fetch } : {}),
    })

  if (!useMedia) {
    const outcome = await sendTextParts(parts, sendPart)
    return {
      delivered: outcome.ok,
      mediaCount: 0,
      ...(outcome.reason === undefined ? {} : { deliveryReason: outcome.reason }),
    }
  }

  // Telegram captions are shorter than message text; the rest goes as messages.
  const captionParts = text.length === 0 ? [] : splitForWechat(text, TELEGRAM_CAPTION_LIMIT)
  const caption = captionParts[0]
  const remainderSource = captionParts.slice(1).join("\n")
  let mediaSent = 0
  const reasons: string[] = []
  for (const [index, attachment] of parsed.attachments.entries()) {
    const resolved = await resolveOutboundAttachment(attachment, env)
    if (!resolved.ok) {
      reasons.push(resolved.reason)
      continue
    }
    const upload = await sendTelegramOutboundMedia({
      token: config.token,
      chatId: config.chatId,
      attachment,
      bytes: resolved.bytes,
      ...(index === 0 && caption ? { caption } : {}),
      ...(config.fetch ? { fetch: config.fetch } : {}),
    })
    if (upload.ok) mediaSent += 1
    else reasons.push(upload.reason)
  }
  const remainder =
    mediaSent === 0
      ? parts
      : remainderSource.length === 0
        ? []
        : splitForWechat(remainderSource, CHANNEL_TEXT_LIMIT)
  const outcome = await sendTextParts(remainder, sendPart)
  const deliveryReason = [reasons.join("; "), outcome.reason].filter(
    (reason): reason is string => typeof reason === "string" && reason.length > 0,
  )
  return {
    delivered: outcome.ok && (mediaSent > 0 || parts.length > 0),
    mediaCount: mediaSent,
    ...(deliveryReason.length === 0 ? {} : { deliveryReason: deliveryReason.join("; ") }),
  }
}

/**
 * D74 T4 (audit #20 SEC-006): wrap return values in Secret<T> so
 * accidental `console.log(slackBotToken())` prints `[REDACTED]` instead
 * of the cleartext token. Mirrors packages/adapters/src/wechat/secret.ts
 * adopted at ilink.ts:206 (D72 T3).
 *
 * Callers must `.unwrap()` at the fetch call site (HTTP header
 * construction). The verbose call site is intentional — every
 * `.unwrap()` is a code-review signal.
 */
export function slackBotToken(env: NodeJS.ProcessEnv = process.env): Secret<string> {
  return Secret.create((env["BUTLER_V5_SLACK_BOT_TOKEN"] ?? "").trim())
}

export function telegramBotToken(env: NodeJS.ProcessEnv = process.env): Secret<string> {
  return Secret.create((env["BUTLER_V5_TELEGRAM_BOT_TOKEN"] ?? "").trim())
}

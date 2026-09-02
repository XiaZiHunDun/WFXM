import {
  channelOutboundMediaEnabled,
  parseChannelOutboundMedia,
  resolveOutboundAttachment,
  sendTelegramOutboundMedia,
} from "./channel-outbound-media.js"
import { sendSlackOutboundFile, sendSlackOutboundMessage } from "@butler/adapters/slack/index.js"

export type ChannelOutboundResult =
  | { readonly ok: true }
  | { readonly ok: false; readonly reason: string }

export interface TelegramOutboundConfig {
  readonly token: string
  readonly chatId: string
  readonly text: string
  readonly fetch?: typeof fetch
  readonly timeoutMs?: number
}

const TELEGRAM_API = "https://api.telegram.org"

function clipOutboundText(text: string, maxChars: number): string {
  const trimmed = text.trim()
  if (trimmed.length <= maxChars) return trimmed
  return `${trimmed.slice(0, Math.max(0, maxChars - 1))}…`
}

export async function sendTelegramOutboundMessage(
  config: TelegramOutboundConfig,
): Promise<ChannelOutboundResult> {
  const token = config.token.trim()
  if (!token) return { ok: false, reason: "telegram bot token is required" }
  const chatId = config.chatId.trim()
  if (!chatId) return { ok: false, reason: "telegram chat_id is required" }
  const text = clipOutboundText(config.text, 3900)
  if (!text) return { ok: false, reason: "reply is empty" }

  const fetchFn = config.fetch ?? fetch
  const controller = new AbortController()
  const timeoutMs = config.timeoutMs ?? 15_000
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
    let parsed: { readonly ok?: boolean; readonly description?: string }
    try {
      parsed = JSON.parse(raw) as typeof parsed
    } catch {
      return { ok: false, reason: `telegram API non-JSON: ${raw.slice(0, 200)}` }
    }
    if (!res.ok || !parsed.ok) {
      return {
        ok: false,
        reason: parsed.description ?? `telegram API HTTP ${res.status}`,
      }
    }
    return { ok: true }
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      return { ok: false, reason: `telegram API timeout after ${timeoutMs}ms` }
    }
    return { ok: false, reason: err instanceof Error ? err.message : String(err) }
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
  const parsed = parseChannelOutboundMedia(config.reply)
  const useMedia = channelOutboundMediaEnabled(env) && parsed.attachments.length > 0
  let mediaSent = 0
  const reasons: string[] = []

  if (useMedia) {
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
        ...(mediaSent === 0 && parsed.text ? { comment: parsed.text } : {}),
        ...(config.threadTs ? { threadTs: config.threadTs } : {}),
        ...(config.fetch ? { fetch: config.fetch } : {}),
      })
      if (upload.ok) mediaSent += 1
      else reasons.push(upload.reason)
    }
    if (parsed.text && mediaSent === 0) {
      const textOnly = await sendSlackOutboundMessage({
        token: config.token,
        channel: config.channel,
        text: parsed.text,
        ...(config.threadTs ? { threadTs: config.threadTs } : {}),
        ...(config.fetch ? { fetch: config.fetch } : {}),
      })
      return {
        delivered: textOnly.ok,
        mediaCount: 0,
        ...(textOnly.ok ? {} : { deliveryReason: textOnly.reason }),
      }
    }
    return {
      delivered: mediaSent > 0,
      mediaCount: mediaSent,
      ...(reasons.length > 0 ? { deliveryReason: reasons.join("; ") } : {}),
    }
  }

  const outbound = await sendSlackOutboundMessage({
    token: config.token,
    channel: config.channel,
    text: config.reply,
    ...(config.threadTs ? { threadTs: config.threadTs } : {}),
    ...(config.fetch ? { fetch: config.fetch } : {}),
  })
  return {
    delivered: outbound.ok,
    mediaCount: 0,
    ...(outbound.ok ? {} : { deliveryReason: outbound.reason }),
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
  const parsed = parseChannelOutboundMedia(config.reply)
  const useMedia = channelOutboundMediaEnabled(env) && parsed.attachments.length > 0
  let mediaSent = 0
  const reasons: string[] = []

  if (useMedia) {
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
        ...(index === 0 && parsed.text ? { caption: parsed.text } : {}),
        ...(config.fetch ? { fetch: config.fetch } : {}),
      })
      if (upload.ok) mediaSent += 1
      else reasons.push(upload.reason)
    }
    if (parsed.text && mediaSent === 0) {
      const textOnly = await sendTelegramOutboundMessage({
        token: config.token,
        chatId: config.chatId,
        text: parsed.text,
        ...(config.fetch ? { fetch: config.fetch } : {}),
      })
      return {
        delivered: textOnly.ok,
        mediaCount: 0,
        ...(textOnly.ok ? {} : { deliveryReason: textOnly.reason }),
      }
    }
    return {
      delivered: mediaSent > 0,
      mediaCount: mediaSent,
      ...(reasons.length > 0 ? { deliveryReason: reasons.join("; ") } : {}),
    }
  }

  const outbound = await sendTelegramOutboundMessage({
    token: config.token,
    chatId: config.chatId,
    text: config.reply,
    ...(config.fetch ? { fetch: config.fetch } : {}),
  })
  return {
    delivered: outbound.ok,
    mediaCount: 0,
    ...(outbound.ok ? {} : { deliveryReason: outbound.reason }),
  }
}

export function slackBotToken(env: NodeJS.ProcessEnv = process.env): string {
  return (env["BUTLER_V5_SLACK_BOT_TOKEN"] ?? "").trim()
}

export function telegramBotToken(env: NodeJS.ProcessEnv = process.env): string {
  return (env["BUTLER_V5_TELEGRAM_BOT_TOKEN"] ?? "").trim()
}

export function slackOutboundEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return slackBotToken(env).length > 0
}

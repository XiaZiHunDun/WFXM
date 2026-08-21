export type ChannelOutboundResult =
  | { readonly ok: true }
  | { readonly ok: false; readonly reason: string }

export interface SlackOutboundConfig {
  readonly token: string
  readonly channel: string
  readonly text: string
  readonly threadTs?: string
  readonly fetch?: typeof fetch
  readonly timeoutMs?: number
}

export interface TelegramOutboundConfig {
  readonly token: string
  readonly chatId: string
  readonly text: string
  readonly fetch?: typeof fetch
  readonly timeoutMs?: number
}

const SLACK_API = "https://slack.com/api/chat.postMessage"
const TELEGRAM_API = "https://api.telegram.org"

function clipOutboundText(text: string, maxChars: number): string {
  const trimmed = text.trim()
  if (trimmed.length <= maxChars) return trimmed
  return `${trimmed.slice(0, Math.max(0, maxChars - 1))}…`
}

export async function sendSlackOutboundMessage(
  config: SlackOutboundConfig,
): Promise<ChannelOutboundResult> {
  const token = config.token.trim()
  if (!token) return { ok: false, reason: "slack bot token is required" }
  const channel = config.channel.trim()
  if (!channel) return { ok: false, reason: "slack channel is required" }
  const text = clipOutboundText(config.text, 3900)
  if (!text) return { ok: false, reason: "reply is empty" }

  const fetchFn = config.fetch ?? fetch
  const controller = new AbortController()
  const timeoutMs = config.timeoutMs ?? 15_000
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetchFn(SLACK_API, {
      method: "POST",
      headers: {
        authorization: `Bearer ${token}`,
        "content-type": "application/json; charset=utf-8",
      },
      body: JSON.stringify({
        channel,
        text,
        ...(config.threadTs ? { thread_ts: config.threadTs } : {}),
      }),
      signal: controller.signal,
    })
    const raw = await res.text()
    let parsed: { readonly ok?: boolean; readonly error?: string }
    try {
      parsed = JSON.parse(raw) as typeof parsed
    } catch {
      return { ok: false, reason: `slack API non-JSON: ${raw.slice(0, 200)}` }
    }
    if (!res.ok || !parsed.ok) {
      return {
        ok: false,
        reason: parsed.error ?? `slack API HTTP ${res.status}`,
      }
    }
    return { ok: true }
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      return { ok: false, reason: `slack API timeout after ${timeoutMs}ms` }
    }
    return { ok: false, reason: err instanceof Error ? err.message : String(err) }
  } finally {
    clearTimeout(timer)
  }
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

export function slackBotToken(env: NodeJS.ProcessEnv = process.env): string {
  return (env["BUTLER_V5_SLACK_BOT_TOKEN"] ?? "").trim()
}

export function telegramBotToken(env: NodeJS.ProcessEnv = process.env): string {
  return (env["BUTLER_V5_TELEGRAM_BOT_TOKEN"] ?? "").trim()
}

export function slackOutboundEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return slackBotToken(env).length > 0
}

export function telegramOutboundEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return telegramBotToken(env).length > 0
}

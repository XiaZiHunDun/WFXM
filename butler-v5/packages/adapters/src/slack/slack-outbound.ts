/**
 * Slack chat.postMessage via Web API. Pure HTTP, no state.
 *
 * Configurable fetch for test injection. 15s default timeout.
 * Clips reply text to 3900 chars (Slack limit is ~40000 but blocks
 * UI rendering; 3900 leaves headroom).
 */

export type SlackOutboundResult =
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

const SLACK_API = "https://slack.com/api/chat.postMessage"

function clipOutboundText(text: string, maxChars: number): string {
  const trimmed = text.trim()
  if (trimmed.length <= maxChars) return trimmed
  return `${trimmed.slice(0, Math.max(0, maxChars - 1))}…`
}

export async function sendSlackOutboundMessage(
  config: SlackOutboundConfig,
): Promise<SlackOutboundResult> {
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
/**
 * Slack files.upload via Web API (multipart form). Pure HTTP, no state.
 *
 * Caller is responsible for resolving the file path + bytes (see
 * `apps/api/src/channel-outbound-media.ts` `resolveOutboundAttachment`
 * which enforces allowed-roots + size guard). This module only does the
 * upload — 30s default timeout.
 */
import type { SlackOutboundResult } from "./slack-outbound.js"

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
}): Promise<SlackOutboundResult> {
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
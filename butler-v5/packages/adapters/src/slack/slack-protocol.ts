/**
 * Slack Events API: signing secret verification + event payload parsing.
 *
 * - `verifySlackSignature`: HMAC SHA256 over `v0:{ts}:{rawBody}`, 5-min
 *   replay window, constant-time compare. Returns false on any missing
 *   field or out-of-window timestamp.
 * - `parseSlackEventPayload`: dispatch on body `type`. `url_verification`
 *   yields challenge; `event_callback` with `message` (incl. file_share /
 *   file_comment subtype) yields message; everything else is `ignore`.
 *
 * Pure functions, no I/O.
 */
import { createHmac, timingSafeEqual } from "node:crypto"
import { describeSlackFiles, type ChannelInboundMedia } from "./slack-media.js"

export function verifySlackSignature(
  signingSecret: string,
  timestamp: string,
  signature: string,
  rawBody: string,
  nowMs = Date.now(),
): boolean {
  if (!signingSecret || !timestamp || !signature) return false
  const ts = Number(timestamp)
  if (!Number.isFinite(ts)) return false
  if (Math.abs(nowMs - ts * 1000) > 5 * 60_000) return false
  const base = `v0:${timestamp}:${rawBody}`
  const digest = `v0=${createHmac("sha256", signingSecret).update(base).digest("hex")}`
  const a = Buffer.from(digest)
  const b = Buffer.from(signature)
  if (a.length !== b.length) return false
  return timingSafeEqual(a, b)
}

export type SlackWebhookParseResult =
  | { readonly kind: "challenge"; readonly challenge: string }
  | {
      readonly kind: "message"
      readonly fromSubject: string
      readonly content: string
      readonly messageId: string
      readonly deliveryChannel: string
      readonly threadTs?: string
      readonly media?: readonly ChannelInboundMedia[]
    }
  | { readonly kind: "ignore" }
  | { readonly kind: "invalid"; readonly reason: string }

export function parseSlackEventPayload(body: unknown): SlackWebhookParseResult {
  if (!body || typeof body !== "object") {
    return { kind: "invalid", reason: "body must be an object" }
  }
  const rec = body as Record<string, unknown>
  if (rec["type"] === "url_verification") {
    const challenge = rec["challenge"]
    if (typeof challenge !== "string") {
      return { kind: "invalid", reason: "missing challenge" }
    }
    return { kind: "challenge", challenge }
  }
  if (rec["type"] !== "event_callback") {
    return { kind: "ignore" }
  }
  const event = rec["event"]
  if (!event || typeof event !== "object") {
    return { kind: "ignore" }
  }
  const ev = event as Record<string, unknown>
  if (ev["type"] !== "message") {
    return { kind: "ignore" }
  }
  const subtype = ev["subtype"]
  if (
    subtype !== undefined &&
    subtype !== null &&
    subtype !== "file_share" &&
    subtype !== "file_comment"
  ) {
    return { kind: "ignore" }
  }
  const user = ev["user"]
  const text = typeof ev["text"] === "string" ? ev["text"].trim() : ""
  const ts = ev["ts"]
  const channel = ev["channel"]
  const threadTs = ev["thread_ts"]
  if (typeof user !== "string" || typeof channel !== "string" || !channel.trim()) {
    return { kind: "ignore" }
  }
  const fileContent = describeSlackFiles(ev["files"], text)
  const content = fileContent?.content ?? text
  if (!content) return { kind: "ignore" }
  return {
    kind: "message",
    fromSubject: user,
    content,
    messageId: typeof ts === "string" ? `slack-${ts}` : `slack-${Date.now()}`,
    deliveryChannel: channel.trim(),
    ...(fileContent?.media ? { media: fileContent.media } : {}),
    ...(typeof threadTs === "string" && threadTs.trim()
      ? { threadTs: threadTs.trim() }
      : typeof ts === "string" && ts.trim()
        ? { threadTs: ts.trim() }
        : {}),
  }
}
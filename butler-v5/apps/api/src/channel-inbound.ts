import { createHmac, timingSafeEqual } from "node:crypto"
import { buildChannelRunTrigger } from "@butler/domain/runtime.js"
import type { Wiring } from "./wiring.js"
import { defaultChannelConversationId, parseClientConversationId } from "./conversation-id.js"
import { isChannelAllowed, parseAllowedChannelIds } from "./channel-config.js"
import { runButlerLoop } from "./wechat-inbound-butler.js"
import {
  describeSlackFiles,
  describeTelegramMedia,
  type ChannelInboundMedia,
} from "./channel-media.js"

export interface ChannelInboundInput {
  readonly wiring: Wiring
  readonly channelId: string
  readonly fromSubject: string
  readonly content: string
  readonly messageId?: string
  readonly conversationId?: unknown
}

export interface ChannelInboundResult {
  readonly conversationId: string
  readonly turnId: string
  readonly channelId: string
  readonly reply: string
  readonly meta: {
    readonly iterations: number
    readonly toolCalls: number
    readonly finalDecision: string
    readonly traces: readonly string[]
  }
}

export async function handleChannelInbound(
  input: ChannelInboundInput,
): Promise<ChannelInboundResult> {
  const channelId = input.channelId.trim()
  const fromSubject = input.fromSubject.trim()
  if (!channelId || !fromSubject) {
    throw new ChannelInboundError("invalid body", 400)
  }
  const allowlist = parseAllowedChannelIds(process.env)
  if (!isChannelAllowed(channelId, allowlist)) {
    throw new ChannelInboundError("channel not allowed", 403)
  }
  const parsedId = parseClientConversationId(input.conversationId)
  if (parsedId.kind === "invalid") {
    throw new ChannelInboundError(`invalid conversationId: ${parsedId.reason}`, 400)
  }
  const conversationId =
    parsedId.kind === "valid"
      ? parsedId.value
      : defaultChannelConversationId(channelId, fromSubject)
  const turnId = `turn-${Date.now()}`
  const projectId = `channel:${channelId}`
  await input.wiring.eventBridge.appendConversationEvent({
    streamId: conversationId,
    eventId: `evt-${Date.now()}-channel-${input.messageId ?? "no-msgid"}`,
    eventType: "ConversationStarted",
    correlationId: `corr-${Date.now()}-${fromSubject}`,
    actor: { kind: "system", id: "channel-intake" },
    event: {
      _tag: "ConversationStarted",
      projectId,
      content: input.content,
      fromUserId: fromSubject,
      channelId,
    },
  })
  const loopResult = await runButlerLoop({
    wiring: input.wiring,
    conversationId,
    content: input.content,
    fromUserId: fromSubject,
    projectId,
    idempotencyKey: input.messageId ?? `channel-${conversationId}-${turnId}`,
    runTrigger: buildChannelRunTrigger({
      channelId,
      fromSubject,
      conversationId,
      content: input.content,
      ...(input.messageId ? { messageId: input.messageId } : {}),
    }),
  })
  return {
    conversationId,
    turnId,
    channelId,
    reply: loopResult.reply,
    meta: {
      iterations: loopResult.iterations,
      toolCalls: loopResult.toolCalls,
      finalDecision: loopResult.finalDecision,
      traces: loopResult.traces,
    },
  }
}

export class ChannelInboundError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = "ChannelInboundError"
  }
}

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

export type TelegramWebhookParseResult =
  | {
      readonly kind: "message"
      readonly fromSubject: string
      readonly content: string
      readonly messageId: string
      readonly media?: readonly ChannelInboundMedia[]
    }
  | { readonly kind: "ignore" }
  | { readonly kind: "invalid"; readonly reason: string }

export function parseTelegramUpdate(body: unknown): TelegramWebhookParseResult {
  if (!body || typeof body !== "object") {
    return { kind: "invalid", reason: "body must be an object" }
  }
  const update = body as Record<string, unknown>
  const message = update["message"]
  if (!message || typeof message !== "object") {
    return { kind: "ignore" }
  }
  const msg = message as Record<string, unknown>
  const from = msg["from"]
  const messageId = msg["message_id"]
  if (!from || typeof from !== "object") {
    return { kind: "ignore" }
  }
  const fromRec = from as Record<string, unknown>
  const userId = fromRec["id"]
  if (typeof userId !== "number" && typeof userId !== "string") {
    return { kind: "ignore" }
  }
  const text = typeof msg["text"] === "string" ? msg["text"].trim() : ""
  const mediaContent = describeTelegramMedia(msg)
  const content = mediaContent?.content ?? text
  if (!content) return { kind: "ignore" }
  return {
    kind: "message",
    fromSubject: String(userId),
    content,
    messageId:
      typeof messageId === "number" || typeof messageId === "string"
        ? `telegram-${String(messageId)}`
        : `telegram-${Date.now()}`,
    ...(mediaContent?.media ? { media: mediaContent.media } : {}),
  }
}

export function telegramWebhookAuthorized(
  env: NodeJS.ProcessEnv,
  headerSecret: string | undefined,
): boolean {
  const expected = (env["BUTLER_V5_TELEGRAM_WEBHOOK_SECRET"] ?? "").trim()
  if (!expected) return true
  return (headerSecret ?? "").trim() === expected
}

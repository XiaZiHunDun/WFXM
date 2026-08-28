import { normalizeChannelInbound } from "@butler/runtime/intake/index.js"
import type { Wiring } from "./wiring.js"
import { isChannelAllowed, parseAllowedChannelIds } from "./channel-config.js"
import { runButlerLoop } from "./wechat-inbound-butler.js"
import { describeTelegramMedia, type ChannelInboundMedia } from "./channel-media.js"

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
  const allowlist = parseAllowedChannelIds(process.env)
  const channelId = input.channelId.trim()
  if (!isChannelAllowed(channelId, allowlist)) {
    throw new ChannelInboundError("channel not allowed", 403)
  }
  const normalized = normalizeChannelInbound({
    channelId: input.channelId,
    fromSubject: input.fromSubject,
    content: input.content,
    ...(input.messageId ? { messageId: input.messageId } : {}),
    conversationId: input.conversationId,
  })
  if (!normalized.ok) {
    const message =
      normalized.error.kind === "invalid_conversation_id"
        ? `invalid conversationId: ${normalized.error.reason}`
        : normalized.error.reason
    throw new ChannelInboundError(message, 400)
  }
  const { value } = normalized
  await input.wiring.eventBridge.appendConversationEvent({
    streamId: value.conversationId,
    eventId: `evt-${Date.now()}-channel-${input.messageId ?? "no-msgid"}`,
    eventType: "ConversationStarted",
    correlationId: `corr-${Date.now()}-${value.subject}`,
    actor: { kind: "system", id: "channel-intake" },
    event: {
      _tag: "ConversationStarted",
      projectId: value.projectId,
      content: value.content,
      fromUserId: value.subject,
      channelId,
    },
  })
  const loopResult = await runButlerLoop({
    wiring: input.wiring,
    conversationId: value.conversationId,
    content: value.content,
    fromUserId: value.subject,
    projectId: value.projectId,
    idempotencyKey: value.idempotencyKey,
    runTrigger: value.runTrigger,
  })
  return {
    conversationId: value.conversationId,
    turnId: value.turnId,
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

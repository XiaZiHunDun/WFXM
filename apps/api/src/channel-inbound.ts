import { normalizeChannelInbound } from "@butler/runtime/intake/index.js"
import type { ChannelKind, ChannelPort } from "@butler/ports/core/channel.js"
import type { Wiring } from "./wiring.js"
import {
  isChannelAllowed,
  parseAllowedChannelIds,
  resolveChannelProjectId,
  type ChannelEngine,
} from "./channel-config.js"
import type { ButlerAssembly } from "./butler-assembly.js"
import { handleButlerInbound } from "./butler-inbound.js"
import type { ButlerRuntimeProvider } from "./butler-runtime-provider.js"
import { runButlerLoop } from "./wechat-inbound-butler.js"
import { describeTelegramMedia, type ChannelInboundMedia } from "./channel-media.js"
import { checkInboundOrder, type InboundOrderSkipReason } from "./inbound-ordering.js"
import { timingSafeEqualStrings } from "./lib/secure-compare.js"

export interface ChannelInboundInput {
  readonly wiring: Wiring
  readonly channelId: string
  readonly fromSubject: string
  readonly content: string
  readonly messageId?: string
  readonly conversationId?: unknown
  /** Monotonic per-conversation ordering hint from the channel (optional). */
  readonly sequence?: number
  /** Source message time in epoch milliseconds (optional). */
  readonly occurredAtMs?: number
  /** Per-channel cutover switch; omit/legacy keeps the RunEngine pipeline. */
  readonly engine?: ChannelEngine
  readonly butler?: ButlerRuntimeProvider
  /** Outbound port used by the butler pipeline; a no-op is used when omitted. */
  readonly channel?: ChannelPort
  readonly ownerThreadTs?: string
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
  /** Butler pipeline only: whether the reply reached the channel. */
  readonly delivered?: boolean
  readonly deliveryReason?: string
  /** True when an older/out-of-order message was dropped before any run. */
  readonly skipped?: boolean
  readonly skipReason?: InboundOrderSkipReason
}

function channelKindOf(channelId: string): ChannelKind {
  return channelId === "wechat" || channelId === "slack" || channelId === "telegram"
    ? channelId
    : "generic"
}

export async function handleChannelInbound(
  input: ChannelInboundInput,
): Promise<ChannelInboundResult> {
  // D64 T3 (audit #9 F-04 cross-channel wiring): telegram inbound
  // inherits approval-fatigue mitigation wired inside `runButlerLoop`,
  // dispatched as `channel: "telegram"` by channelId. Channel-specific
  // prompt rendering is the caller's responsibility — this entry point
  // does not call evaluateChannelApproval directly because tool name
  // and args are only known at tool-execution time (inside the loop),
  // not at intake. The fatigue decision lands as either an inline
  // cooldown sleep or a RunPauseForApproval surfaced back to telegram
  // via the existing approval-resume flow.
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
  const ordering = checkInboundOrder({
    channelId,
    conversationId: value.conversationId,
    ...(input.sequence === undefined ? {} : { sequence: input.sequence }),
    ...(input.occurredAtMs === undefined ? {} : { occurredAtMs: input.occurredAtMs }),
  })
  if (!ordering.ok) {
    return {
      conversationId: value.conversationId,
      turnId: value.turnId,
      channelId,
      reply: "",
      meta: {
        iterations: 0,
        toolCalls: 0,
        finalDecision: "Skip",
        traces: [`inbound-order:${ordering.reason}`],
      },
      skipped: true,
      skipReason: ordering.reason,
    }
  }
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

  if (input.engine === "butler") {
    const provider = input.butler
    if (!provider) {
      throw new ChannelInboundError("butler runtime unavailable: provider not configured", 503)
    }
    let runtime: ButlerAssembly
    try {
      runtime = await provider.assembly()
    } catch (error) {
      throw new ChannelInboundError(
        `butler runtime unavailable: ${error instanceof Error ? error.message : String(error)}`,
        503,
      )
    }
    const channelKind = channelKindOf(channelId)
    provider.rememberOwner(value.conversationId, {
      channelKind,
      address: value.subject,
      ...(input.ownerThreadTs === undefined ? {} : { threadTs: input.ownerThreadTs }),
    })
    const channel: ChannelPort = input.channel ?? {
      channelKind,
      async sendText() {
        // Generic intake returns the reply in the HTTP body.
        return { ok: true, messageId: null }
      },
    }
    const outcome = await handleButlerInbound({
      butler: runtime.butler,
      channel,
      recipient: { address: value.subject, channelKind },
      input: {
        conversationId: value.conversationId,
        userId: value.subject,
        projectId: resolveChannelProjectId(channelId, process.env),
        content: value.content,
      },
    })
    return {
      conversationId: value.conversationId,
      turnId: value.turnId,
      channelId,
      reply: outcome.result.reply,
      meta: {
        iterations: 0,
        toolCalls: 0,
        finalDecision: "Respond",
        traces: outcome.result.traces,
      },
      delivered: outcome.sent,
      ...(outcome.sendError === undefined ? {} : { deliveryReason: outcome.sendError }),
    }
  }

  const loopResult = await runButlerLoop({
    wiring: input.wiring,
    conversationId: value.conversationId,
    content: value.content,
    fromUserId: value.subject,
    projectId: value.projectId,
    idempotencyKey: value.idempotencyKey,
    turnId: value.turnId,
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
      /** Telegram's per-chat monotonic message id, when numeric. */
      readonly sequence?: number
      readonly occurredAtMs?: number
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
  const numericMessageId =
    typeof messageId === "number"
      ? messageId
      : typeof messageId === "string" && messageId.trim() !== ""
        ? Number(messageId)
        : Number.NaN
  const date = msg["date"]
  const occurredAtMs =
    typeof date === "number" && Number.isFinite(date) && date > 0 ? date * 1000 : undefined
  return {
    kind: "message",
    fromSubject: String(userId),
    content,
    messageId:
      typeof messageId === "number" || typeof messageId === "string"
        ? `telegram-${String(messageId)}`
        : `telegram-${Date.now()}`,
    ...(Number.isFinite(numericMessageId) ? { sequence: numericMessageId } : {}),
    ...(occurredAtMs === undefined ? {} : { occurredAtMs }),
    ...(mediaContent?.media ? { media: mediaContent.media } : {}),
  }
}

export function telegramWebhookAuthorized(
  env: NodeJS.ProcessEnv,
  headerSecret: string | undefined,
): boolean {
  const expected = (env["BUTLER_V5_TELEGRAM_WEBHOOK_SECRET"] ?? "").trim()
  // D62 T4 (audit #1 F-07): FAIL-CLOSED when secret is unset. Previously
  // returned true (FAIL-OPEN) which meant any client POSTing to the
  // /telegram webhook would be accepted without auth — auth-bypass
  // vulnerability when operator forgot to configure the secret.
  if (!expected) return false
  // D72 T3 (audit #18 SEC-001): timing-safe compare to prevent byte-level
  // timing leaks. Length mismatch returns false before timingSafeEqual
  // (timingSafeEqual throws on unequal length, but we want a stable
  // boolean). Both sides are trimmed first; trim() can vary in length
  // per request but the compare is over the trimmed values.
  // D73 SEC-004: helper promoted to lib/secure-compare.ts so channel-inbound
  // + inbound-shared-secret + future sites share one source of truth.
  const provided = (headerSecret ?? "").trim()
  if (provided.length !== expected.length) return false
  return timingSafeEqualStrings(provided, expected)
}

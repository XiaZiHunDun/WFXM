/**
 * Intake normalize — identity, conversationId, idempotency, RunTrigger.
 *
 * No Loop / Policy / persistence. Delivery shells (apps/api) call these
 * after protocol parse + auth, then hand the result to Execution.
 */
import {
  buildChannelRunTrigger,
  buildWechatRunTrigger,
  type RunTrigger,
} from "@butler/domain/runtime.js"
import {
  defaultChannelConversationId,
  defaultWechatConversationId,
  parseClientConversationId,
} from "./conversation-id.js"

export type NormalizeInboundFailure =
  | { readonly kind: "invalid_body"; readonly reason: string }
  | { readonly kind: "invalid_conversation_id"; readonly reason: string }

export type NormalizeInboundResult =
  | { readonly ok: true; readonly value: NormalizedInbound }
  | { readonly ok: false; readonly error: NormalizeInboundFailure }

export interface NormalizedInbound {
  readonly conversationId: string
  readonly turnId: string
  readonly projectId: string
  readonly subject: string
  readonly content: string
  readonly messageId: string | undefined
  readonly idempotencyKey: string
  readonly runTrigger: RunTrigger
  readonly source: "wechat" | "channel"
}

function resolveConversationId(
  raw: unknown,
  fallback: () => string,
):
  | { readonly ok: true; readonly conversationId: string }
  | { readonly ok: false; readonly error: NormalizeInboundFailure } {
  const parsed = parseClientConversationId(raw)
  if (parsed.kind === "invalid") {
    return {
      ok: false,
      error: { kind: "invalid_conversation_id", reason: parsed.reason },
    }
  }
  return {
    ok: true,
    conversationId: parsed.kind === "valid" ? parsed.value : fallback(),
  }
}

export function normalizeWechatInbound(input: {
  readonly fromUserId: string
  readonly content: string
  readonly messageId?: string
  readonly projectId?: string
  readonly conversationId?: unknown
  readonly nowMs?: number
}): NormalizeInboundResult {
  const fromUserId = input.fromUserId.trim()
  const content = input.content
  if (!fromUserId) {
    return { ok: false, error: { kind: "invalid_body", reason: "fromUserId is required" } }
  }
  if (typeof content !== "string") {
    return { ok: false, error: { kind: "invalid_body", reason: "content is required" } }
  }
  const projectId = (input.projectId ?? "wechat").trim() || "wechat"
  const resolved = resolveConversationId(input.conversationId, () =>
    defaultWechatConversationId(projectId, fromUserId),
  )
  if (!resolved.ok) return resolved
  const nowMs = input.nowMs ?? Date.now()
  const turnId = `turn-${nowMs}`
  const messageId = input.messageId?.trim() || undefined
  const idempotencyKey = messageId ?? `wechat-${resolved.conversationId}-${turnId}`
  const runTrigger = buildWechatRunTrigger({
    userId: fromUserId,
    conversationId: resolved.conversationId,
    content,
    messageId: idempotencyKey,
  })
  return {
    ok: true,
    value: {
      conversationId: resolved.conversationId,
      turnId,
      projectId,
      subject: fromUserId,
      content,
      messageId,
      idempotencyKey,
      runTrigger,
      source: "wechat",
    },
  }
}

export function normalizeChannelInbound(input: {
  readonly channelId: string
  readonly fromSubject: string
  readonly content: string
  readonly messageId?: string
  readonly conversationId?: unknown
  readonly nowMs?: number
}): NormalizeInboundResult {
  const channelId = input.channelId.trim()
  const fromSubject = input.fromSubject.trim()
  const content = input.content
  if (!channelId || !fromSubject) {
    return {
      ok: false,
      error: { kind: "invalid_body", reason: "channelId and fromSubject are required" },
    }
  }
  if (typeof content !== "string") {
    return { ok: false, error: { kind: "invalid_body", reason: "content is required" } }
  }
  const resolved = resolveConversationId(input.conversationId, () =>
    defaultChannelConversationId(channelId, fromSubject),
  )
  if (!resolved.ok) return resolved
  const nowMs = input.nowMs ?? Date.now()
  const turnId = `turn-${nowMs}`
  const projectId = `channel:${channelId}`
  const messageId = input.messageId?.trim() || undefined
  const idempotencyKey = messageId ?? `channel-${resolved.conversationId}-${turnId}`
  const runTrigger = buildChannelRunTrigger({
    channelId,
    fromSubject,
    conversationId: resolved.conversationId,
    content,
    ...(messageId ? { messageId } : {}),
  })
  return {
    ok: true,
    value: {
      conversationId: resolved.conversationId,
      turnId,
      projectId,
      subject: fromSubject,
      content,
      messageId,
      idempotencyKey,
      runTrigger,
      source: "channel",
    },
  }
}

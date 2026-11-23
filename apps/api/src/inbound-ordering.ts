/**
 * Per-conversation inbound ordering guard.
 *
 * Webhooks can deliver messages out of order (Slack retries, Telegram
 * redeliveries, slow upstreams). Executing the older message after a newer
 * one overwrites the newer conversation state. This guard rejects a message
 * that is strictly older than the newest one already seen for the same
 * conversation.
 *
 * Ordering metadata is optional: channels that do not expose a sequence or
 * timestamp (or omit it) always pass. State is process-local and bounded; a
 * multi-process deployment needs a shared implementation before relying on
 * this across replicas.
 */

export const DEFAULT_INBOUND_ORDER_WINDOW_MS = 120_000
const MAX_TRACKED_CONVERSATIONS = 5_000

interface ConversationOrder {
  readonly lastSequence?: number
  readonly lastOccurredAtMs?: number
}

const seen = new Map<string, ConversationOrder>()

export type InboundOrderSkipReason = "stale_sequence" | "stale_timestamp"

export type InboundOrderDecision =
  { readonly ok: true } | { readonly ok: false; readonly reason: InboundOrderSkipReason }

export function resolveInboundOrderWindowMs(env: NodeJS.ProcessEnv = process.env): number {
  const raw = (env["BUTLER_V5_INBOUND_ORDER_WINDOW_MS"] ?? "").trim()
  if (!raw) return DEFAULT_INBOUND_ORDER_WINDOW_MS
  const parsed = Number(raw)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : DEFAULT_INBOUND_ORDER_WINDOW_MS
}

function finiteNumber(value: number | undefined): number | undefined {
  return value !== undefined && Number.isFinite(value) ? value : undefined
}

/**
 * `sequence` must be monotonically increasing per conversation (Slack `ts`,
 * Telegram `message_id`). Equality is treated as a redelivery and left to the
 * existing idempotency/replay path; only a strictly older message is rejected.
 */
export function checkInboundOrder(input: {
  readonly channelId: string
  readonly conversationId: string
  readonly sequence?: number
  readonly occurredAtMs?: number
  readonly env?: NodeJS.ProcessEnv
}): InboundOrderDecision {
  const sequence = finiteNumber(input.sequence)
  const occurredRaw = finiteNumber(input.occurredAtMs)
  const occurredAtMs = occurredRaw !== undefined && occurredRaw > 0 ? occurredRaw : undefined
  if (sequence === undefined && occurredAtMs === undefined) return { ok: true }

  const key = `${input.channelId}:${input.conversationId}`
  const previous = seen.get(key)
  const lastSequence = previous?.lastSequence
  const lastOccurredAtMs = previous?.lastOccurredAtMs

  if (sequence !== undefined && lastSequence !== undefined && sequence < lastSequence) {
    return { ok: false, reason: "stale_sequence" }
  }
  const windowMs = resolveInboundOrderWindowMs(input.env)
  if (
    occurredAtMs !== undefined &&
    windowMs > 0 &&
    lastOccurredAtMs !== undefined &&
    occurredAtMs < lastOccurredAtMs - windowMs
  ) {
    return { ok: false, reason: "stale_timestamp" }
  }

  const next: ConversationOrder = {
    ...(sequence === undefined
      ? lastSequence === undefined
        ? {}
        : { lastSequence }
      : { lastSequence: Math.max(sequence, lastSequence ?? sequence) }),
    ...(occurredAtMs === undefined
      ? lastOccurredAtMs === undefined
        ? {}
        : { lastOccurredAtMs }
      : { lastOccurredAtMs: Math.max(occurredAtMs, lastOccurredAtMs ?? occurredAtMs) }),
  }
  // Re-insert so eviction follows least-recently-updated order.
  seen.delete(key)
  seen.set(key, next)
  if (seen.size > MAX_TRACKED_CONVERSATIONS) {
    const oldest = seen.keys().next().value
    if (typeof oldest === "string") seen.delete(oldest)
  }
  return { ok: true }
}

/** Test-only: clear cross-test ordering state. */
export function resetInboundOrdering(): void {
  seen.clear()
}

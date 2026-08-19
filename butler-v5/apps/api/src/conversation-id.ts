/**
 * R8.x.11 — optional client-supplied conversationId for WeChat inbound.
 *
 * Spec: docs/superpowers/specs/2026-08-19-conversation-id-client-supplied-design.md
 *
 * Absent → caller generates a server id.
 * Valid → reuse as stream id (WS can pre-subscribe).
 * Invalid → route returns 400 before the butler loop.
 */

export const CONVERSATION_ID_MAX_LEN = 128
export const CONVERSATION_ID_PATTERN = /^[A-Za-z0-9_.:-]+$/

export type ParseConversationIdResult =
  | { readonly kind: "absent" }
  | { readonly kind: "valid"; readonly value: string }
  | { readonly kind: "invalid"; readonly reason: string }

/**
 * Parse an optional `conversationId` field from an inbound JSON body.
 * `undefined` / `null` mean the client did not supply one.
 */
export function parseClientConversationId(raw: unknown): ParseConversationIdResult {
  if (raw === undefined || raw === null) {
    return { kind: "absent" }
  }
  if (typeof raw !== "string") {
    return { kind: "invalid", reason: "conversationId must be a string" }
  }
  const value = raw.trim()
  if (value.length === 0) {
    return { kind: "invalid", reason: "conversationId must be non-empty" }
  }
  if (value.length > CONVERSATION_ID_MAX_LEN) {
    return {
      kind: "invalid",
      reason: `conversationId exceeds ${CONVERSATION_ID_MAX_LEN} characters`,
    }
  }
  if (!CONVERSATION_ID_PATTERN.test(value)) {
    return {
      kind: "invalid",
      reason: "conversationId contains illegal characters",
    }
  }
  return { kind: "valid", value }
}

/**
 * R8.x.13: stable per-user stream id so WeChat turns share history.
 * Sanitizes project/user so the result always matches CONVERSATION_ID_PATTERN.
 */
export function defaultWechatConversationId(projectId: string, fromUserId: string): string {
  return `c-${sanitizeIdPart(projectId)}-${sanitizeIdPart(fromUserId)}`
}

function sanitizeIdPart(raw: string): string {
  const cleaned = raw
    .trim()
    .replace(/[^A-Za-z0-9_.:-]+/g, "-")
    .replace(/^-+|-+$/g, "")
  const sliced = cleaned.slice(0, 48)
  return sliced.length > 0 ? sliced : "unknown"
}

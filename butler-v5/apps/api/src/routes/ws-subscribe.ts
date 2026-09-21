/**
 * D75 T1 (CQ-005): WS subscribe handler extracted from routes.ts.
 *
 * Owns POST /v1/ws/subscribe. Issues a short-lived WS subscribe token
 * bound to a conversationId + caller identity. Auth:
 *   - BUTLER_V5_INBOUND_SHARED_SECRET header (D69 T4 SEC-3, FAIL-CLOSED)
 *   - caller field restricted to ALLOWED_CALLERS allowlist (D73 SEC-001)
 *     — prevents the shared-secret holder from impersonating arbitrary
 *     callers via self-asserted identifier
 *
 * The issued token is presented to /v1/ws on upgrade; caller + token
 * must match.
 */
import type { Hono } from "hono"
import { parseClientConversationId } from "@butler/runtime/intake/index.js"
import { issueSubscribeToken } from "../ws-subscribe.js"
import { requireInboundSharedSecret } from "../env-util.js"

/**
 * D73 SEC-001: canonical caller allowlist for /v1/ws/subscribe.
 * The token bound to "owner" was previously operator-supplied and
 * unauthenticated — any holder of BUTLER_V5_INBOUND_SHARED_SECRET
 * could mint a token claiming any caller. Restrict the accepted
 * callers to this fixed set; anything else returns 400.
 *
 * First entry is the default when the body omits `caller`. Real
 * bearer-auth caller-binding is pre-scoped for D74+.
 */
const ALLOWED_CALLERS = ["owner", "cli", "wechat-forward"] as const

export function registerWsSubscribeRoutes(app: Hono): void {
  app.post("/v1/ws/subscribe", async (c) => {
    // D69 T4 (audit #10 SEC-3): require BUTLER_V5_INBOUND_SHARED_SECRET
    // header — any unauthenticated caller could mint a WS subscribe token
    // bound to any conversationId, enabling real-time IDOR on the WS push
    // channel. Mirrors the /v1/wechat/inbound auth pattern.
    const denied = requireInboundSharedSecret(process.env, c.req.header("x-inbound-secret"))
    if (denied) return denied
    const body = (await c.req.json().catch(() => null)) as null | {
      apiVersion?: string
      conversationId?: unknown
      /**
       * D72 T3 (audit #18 SEC-003): caller identity to bind to the
       * issued token. Optional — when omitted, defaults to ALLOWANCE_CALLERS[0]
       * ("owner") so legitimate same-process clients keep working without
       * a caller field.
       *
       * D73 SEC-001: the body.caller field was operator-supplied and
       * unauthenticated — any holder of BUTLER_V5_INBOUND_SHARED_SECRET
       * could mint a token bound to caller="owner" (or any name) and
       * impersonate that caller to downstream consumers. Restrict to
       * a fixed allowlist of canonical callers. Real bearer-auth
       * caller-binding is pre-scoped for D74+.
       */
      caller?: string
    }
    if (!body || body.apiVersion !== "v1") {
      return c.text("invalid body", 400)
    }
    const parsedId = parseClientConversationId(body.conversationId)
    if (parsedId.kind !== "valid") {
      return c.text(
        parsedId.kind === "absent"
          ? "conversationId is required"
          : `invalid conversationId: ${parsedId.reason}`,
        400,
      )
    }
    // D73 SEC-001: canonical caller allowlist. Anything outside the set
    // is rejected with 400 — no string fallback, no passthrough. The
    // shared-secret holder can still authenticate, but cannot bind the
    // resulting token to a self-asserted identifier.
    const rawCaller = typeof body.caller === "string" ? body.caller.trim() : ""
    const caller = rawCaller === "" ? ALLOWED_CALLERS[0] : rawCaller
    // ALLOWED_CALLERS is `as const` — Array.includes expects the narrower
    // union, but caller is widened to string. Cast to readonly string[]
    // so the guard narrows back to the allowed union (TS sees includes
    // returning true iff caller is in the set).
    if (!(ALLOWED_CALLERS as readonly string[]).includes(caller)) {
      return c.text(
        `invalid caller: must be one of ${ALLOWED_CALLERS.join(", ")}`,
        400,
      )
    }
    const issued = issueSubscribeToken(parsedId.value, { caller })
    if (!issued) {
      // D63 T4 (audit #9 F-14): token store at cap. Return 503 so the
      // caller knows to retry (after prune on existing tokens).
      return c.text("subscribe token store at capacity", 503)
    }
    // D72 T3 (audit #18 SEC-003) + D73 SEC-001: include caller in wsPath
    // so the WS upgrade can present the matching caller claim. Caller is
    // always present now (allowlist default = "owner").
    const wsPath = `/v1/ws?token=${encodeURIComponent(issued.token)}&caller=${encodeURIComponent(caller)}`
    return c.json(
      {
        conversationId: parsedId.value,
        caller,
        token: issued.token,
        expiresAt: new Date(issued.expiresAtMs).toISOString(),
        wsPath,
      },
      201,
    )
  })
}

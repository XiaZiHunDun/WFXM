/**
 * D75 T1 (CQ-005): channel handler split — top-level glue.
 *
 * routes.ts now owns:
 *   - parseAllowlist (shared env-driven allowlist parser used by the
 *     Slack + Telegram handlers)
 *   - /healthz + /v1/conversations glue
 *   - the createRoutes orchestrator that wires the four extracted
 *     handler modules under apps/api/src/routes/
 *
 * Channel handler bodies moved to:
 *   - routes/inbound.ts          (wechat + generic channel intake)
 *   - routes/slack-events.ts     (Slack webhook)
 *   - routes/telegram-webhook.ts (Telegram webhook)
 *   - routes/ws-subscribe.ts     (WS subscribe token issuer)
 */
import type { Hono } from "hono"
import type { Wiring } from "./wiring.js"
import { registerInboundRoutes } from "./routes/inbound.js"
import { registerSlackEventsRoutes } from "./routes/slack-events.js"
import { registerTelegramWebhookRoutes } from "./routes/telegram-webhook.js"
import { registerWsSubscribeRoutes } from "./routes/ws-subscribe.js"

/**
 * D71 T3 (audit #12 SEC-004 / SEC-005): parse a comma-separated
 * allowlist env var. Returns `null` (allowlist disabled) when the
 * env var is unset/empty; callers must check truthiness before
 * using the returned set so an unset env doesn't accidentally
 * reject every caller.
 */
function parseAllowlist(raw: string | undefined): ReadonlySet<string> | null {
  if (raw === undefined) return null
  const parts = raw
    .split(",")
    .map(s => s.trim())
    .filter(s => s.length > 0)
  if (parts.length === 0) return null
  return new Set(parts)
}

export function createRoutes(app: Hono, wiring: Wiring) {
  app.get("/healthz", (c) => c.json({ status: "ok", wiring: wiring.version }))
  app.post("/v1/conversations", async (c) => {
    // D69 T4 (audit #10 SEC-2): require BUTLER_V5_INBOUND_SHARED_SECRET
    // header — same FAIL-CLOSED pattern as /v1/wechat/inbound (D63 T4).
    // Previously any caller could appendConversationEvent into the event
    // bridge with no auth, enabling event-bridge write DoS if Hono bound
    // beyond loopback.
    const { requireInboundSharedSecret } = await import("./env-util.js")
    const denied = requireInboundSharedSecret(process.env, c.req.header("x-inbound-secret"))
    if (denied) return denied
    const body = (await c.req.json().catch(() => null)) as null | {
      apiVersion?: string
      projectId?: string
      content?: string
    }
    if (
      !body ||
      body.apiVersion !== "v1" ||
      typeof body.projectId !== "string" ||
      typeof body.content !== "string"
    ) {
      return c.text("invalid body", 400)
    }
    const conversationId = `c-${body.projectId}-${Date.now()}`
    await wiring.eventBridge.appendConversationEvent({
      streamId: conversationId,
      eventId: `evt-${Date.now()}-conv`,
      eventType: "ConversationStarted",
      correlationId: `corr-${Date.now()}`,
      actor: { kind: "system", id: "wiring" },
      event: { _tag: "ConversationStarted", projectId: body.projectId, content: body.content },
    })
    return c.json({ conversationId, turnId: `turn-${Date.now()}` }, 201)
  })

  registerInboundRoutes(app, wiring)
  registerSlackEventsRoutes(app, wiring, parseAllowlist)
  registerTelegramWebhookRoutes(app, wiring, parseAllowlist)
  registerWsSubscribeRoutes(app)
}

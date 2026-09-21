/**
 * D75 T1 (CQ-005): Slack events webhook extracted from routes.ts.
 *
 * Owns POST /v1/channel/slack/events. The handler covers three modes:
 *   1. url_verification challenge (Slack onboarding handshake —
 *      signature check is intentionally skipped)
 *   2. event_callback message → handleChannelInbound + outbound reply
 *      with optional per-user allowlist (D71 T3 SEC-005)
 *   3. invalid / ignore responses
 *
 * Signature verification uses Slack's HMAC-SHA256 over (v0 + timestamp
 * + body); the FAIL-CLOSED check lives in verifySlackSignature.
 */
import type { Hono } from "hono"
import type { Wiring } from "../wiring.js"
import { isSlackChannelEnabled } from "../channel-config.js"
import { ChannelInboundError, handleChannelInbound } from "../channel-inbound.js"
import { deliverSlackChannelReply, slackBotToken } from "../channel-outbound.js"
import {
  parseSlackEventPayload,
  verifySlackSignature,
} from "@butler/adapters/slack/index.js"

export function registerSlackEventsRoutes(
  app: Hono,
  wiring: Wiring,
  parseAllowlist: (raw: string | undefined) => ReadonlySet<string> | null,
): void {
  app.post("/v1/channel/slack/events", async (c) => {
    if (!isSlackChannelEnabled(process.env)) {
      return c.text("slack channel disabled", 404)
    }
    const rawBody = await c.req.text()
    let body: unknown
    try {
      body = JSON.parse(rawBody) as unknown
    } catch {
      return c.text("invalid json", 400)
    }
    const parsed = parseSlackEventPayload(body)
    // D63 T4 (audit #9 F-01) — Slack url_verification challenge is the
    // documented exception to signature verification (Slack onboarding
    // handshake). Skip signature check ONLY for challenges; every other
    // event type requires FAIL-CLOSED signature check. Order matters:
    // parse first so we know the event kind, then verify signature.
    if (parsed.kind !== "challenge") {
      const signingSecret = (process.env["BUTLER_V5_SLACK_SIGNING_SECRET"] ?? "").trim()
      const signature = c.req.header("x-slack-signature") ?? ""
      const timestamp = c.req.header("x-slack-request-timestamp") ?? ""
      if (!signingSecret) {
        return c.text("slack signing secret not configured", 401)
      }
      if (!verifySlackSignature(signingSecret, timestamp, signature, rawBody)) {
        return c.text("invalid slack signature", 401)
      }
    }
    // D71 T3 (audit #12 SEC-005): optional per-user allowlist via
    // BUTLER_V5_SLACK_USER_ID_ALLOWLIST (comma-separated). Empty
    // (default) preserves pre-D71 behavior: signed webhooks accepted
    // from any user. Set the env to a comma-separated list of trusted
    // user IDs to harden against a leaked signing-secret scenario
    // where the attacker forges an event from a known user.
    const slackAllowlist = parseAllowlist(process.env["BUTLER_V5_SLACK_USER_ID_ALLOWLIST"])
    if (slackAllowlist && parsed.kind === "message" && parsed.fromSubject) {
      if (!slackAllowlist.has(parsed.fromSubject)) {
        return c.text("slack user not in allowlist", 403)
      }
    }
    if (parsed.kind === "challenge") {
      return c.json({ challenge: parsed.challenge })
    }
    if (parsed.kind === "invalid") {
      return c.text(parsed.reason, 400)
    }
    if (parsed.kind === "ignore") {
      return c.body(null, 204)
    }
    try {
      const result = await handleChannelInbound({
        wiring,
        channelId: "slack",
        fromSubject: parsed.fromSubject,
        content: parsed.content,
        messageId: parsed.messageId,
      })
      let delivered = false
      let deliveryReason: string | undefined
      let mediaCount = 0
      // D74 T4 (audit #20 SEC-006): unwrap Secret<string> at the fetch
      // call site. The verbose .unwrap() is intentional — every site is
      // a code-review signal for where cleartext tokens flow.
      const slackToken = slackBotToken(process.env).unwrap()
      if (slackToken) {
        const outbound = await deliverSlackChannelReply({
          token: slackToken,
          channel: parsed.deliveryChannel,
          reply: result.reply,
          ...(parsed.threadTs ? { threadTs: parsed.threadTs } : {}),
        })
        delivered = outbound.delivered
        mediaCount = outbound.mediaCount
        if (outbound.deliveryReason) deliveryReason = outbound.deliveryReason
      }
      return c.json(
        {
          ok: true,
          reply: result.reply,
          conversationId: result.conversationId,
          delivered,
          mediaCount,
          ...(deliveryReason ? { deliveryReason } : {}),
        },
        200,
      )
    } catch (err) {
      if (err instanceof ChannelInboundError) {
        return c.text(err.message, err.status as 400 | 403)
      }
      throw err
    }
  })
}

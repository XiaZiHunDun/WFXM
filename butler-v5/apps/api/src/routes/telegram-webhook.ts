/**
 * D75 T1 (CQ-005): Telegram webhook handler extracted from routes.ts.
 *
 * Owns POST /v1/channel/telegram/webhook. Key invariants:
 *   - X-Telegram-Bot-Api-Secret-Token header verification (FAIL-CLOSED
 *     when env is unset; mirror of D62 T4 SEC-007)
 *   - Replay dedup via markChannelSeen("telegram", messageId) (D74 T4
 *     SEC-001 — added because Telegram signs webhooks but doesn't
 *     prevent replay within bot-token lifetime)
 *   - Optional per-user allowlist via
 *     BUTLER_V5_TELEGRAM_USER_ID_ALLOWLIST (D71 T3 SEC-004)
 *   - unwrap Secret<string> at the fetch call site (D74 T4 SEC-006)
 */
import type { Hono } from "hono"
import type { Wiring } from "../wiring.js"
import { isTelegramChannelEnabled } from "../channel-config.js"
import {
  ChannelInboundError,
  handleChannelInbound,
  parseTelegramUpdate,
  telegramWebhookAuthorized,
} from "../channel-inbound.js"
import { deliverTelegramChannelReply, telegramBotToken } from "../channel-outbound.js"
import { resolveTelegramInboundContent } from "../channel-media.js"
import { markChannelSeen } from "../lib/channel-seen-ids.js"

export function registerTelegramWebhookRoutes(
  app: Hono,
  wiring: Wiring,
  parseAllowlist: (raw: string | undefined) => ReadonlySet<string> | null,
): void {
  app.post("/v1/channel/telegram/webhook", async (c) => {
    if (!isTelegramChannelEnabled(process.env)) {
      return c.text("telegram channel disabled", 404)
    }
    const secretHeader = c.req.header("x-telegram-bot-api-secret-token")
    if (!telegramWebhookAuthorized(process.env, secretHeader)) {
      return c.text("invalid telegram webhook secret", 401)
    }
    const body = (await c.req.json().catch(() => null)) as unknown
    const parsed = parseTelegramUpdate(body)
    if (parsed.kind === "invalid") {
      return c.text(parsed.reason, 400)
    }
    if (parsed.kind === "ignore") {
      return c.body(null, 204)
    }
    // D74 T4 (audit #20 SEC-001): replay dedup — Telegram signs webhook
    // bodies but doesn't prevent replay within bot-token lifetime.
    // mirror ilink-poller.ts:145-156 dedup pattern. Returns 204
    // (idempotent) on duplicate so the attacker can't observe different
    // behavior between first-send and replay.
    if (parsed.messageId && !markChannelSeen("telegram", parsed.messageId)) {
      return c.body(null, 204)
    }
    // D71 T3 (audit #12 SEC-004): optional per-user allowlist via
    // BUTLER_V5_TELEGRAM_USER_ID_ALLOWLIST (comma-separated). Empty
    // (default) preserves pre-D71 behavior: signed webhooks accepted
    // from any user. Set the env to a comma-separated list of trusted
    // chat/user IDs to harden against a leaked bot-token / hostile
    // signature scenario where the webhook secret is compromised.
    const telegramAllowlist = parseAllowlist(process.env["BUTLER_V5_TELEGRAM_USER_ID_ALLOWLIST"])
    if (telegramAllowlist && !telegramAllowlist.has(parsed.fromSubject)) {
      return c.text("telegram user not in allowlist", 403)
    }
    try {
      const inboundContent = await resolveTelegramInboundContent(parsed, process.env)
      const result = await handleChannelInbound({
        wiring,
        channelId: "telegram",
        fromSubject: parsed.fromSubject,
        content: inboundContent,
        messageId: parsed.messageId,
      })
      let delivered = false
      let deliveryReason: string | undefined
      let mediaCount = 0
      // D74 T4 (audit #20 SEC-006): see Slack handler above.
      const telegramToken = telegramBotToken(process.env).unwrap()
      if (telegramToken) {
        const outbound = await deliverTelegramChannelReply({
          token: telegramToken,
          chatId: parsed.fromSubject,
          reply: result.reply,
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

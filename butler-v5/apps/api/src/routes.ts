import type { Hono } from "hono"
import {
  normalizeWechatInbound,
  parseClientConversationId,
} from "@butler/runtime/intake/index.js"
import type { Wiring } from "./wiring.js"
import {
  isChannelApiEnabled,
  isSlackChannelEnabled,
  isTelegramChannelEnabled,
} from "./channel-config.js"
import {
  ChannelInboundError,
  handleChannelInbound,
  parseTelegramUpdate,
  telegramWebhookAuthorized,
} from "./channel-inbound.js"
import {
  deliverSlackChannelReply,
  deliverTelegramChannelReply,
  slackBotToken,
  telegramBotToken,
} from "./channel-outbound.js"
import { resolveTelegramInboundContent } from "./channel-media.js"
import {
  parseSlackEventPayload,
  verifySlackSignature,
} from "@butler/adapters/slack/index.js"
import { runButlerLoop } from "./wechat-inbound-butler.js"
import { isWechatIntakeEnabled, routeWechatIntake } from "./wechat-intake.js"
import { resolveWechatInboundProjectId } from "./wechat-active-project.js"
import { tryWechatInboundCommand } from "./wechat-inbound-commands.js"
import { issueSubscribeToken } from "./ws-subscribe.js"
import { captureWechatSessionSnapshot } from "./wechat-session-snapshot.js"
import { maybePrependSessionDigest } from "./wechat-session-digest.js"

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
    const expectedInboundSecret = (process.env["BUTLER_V5_INBOUND_SHARED_SECRET"] ?? "").trim()
    if (!expectedInboundSecret) {
      return c.text("inbound shared secret not configured", 401)
    }
    const headerInboundSecret = c.req.header("x-inbound-secret") ?? ""
    if (headerInboundSecret.trim() !== expectedInboundSecret) {
      return c.text("invalid inbound secret", 401)
    }
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
  app.post("/v1/wechat/inbound", async (c) => {
    // D63 T4 (audit #9 F-03): require BUTLER_V5_INBOUND_SHARED_SECRET in
    // env + x-inbound-secret header in request. FAIL-CLOSED when env
    // secret is unset (mirror telegram webhook FAIL-CLOSED from D62 T4
    // F-07 — same auth-bypass class). Previously the handler had zero
    // auth, relying on the implicit loopback-only assumption that broke
    // the moment the Hono server bound to 0.0.0.0 (F-06).
    const expectedInboundSecret = (process.env["BUTLER_V5_INBOUND_SHARED_SECRET"] ?? "").trim()
    if (!expectedInboundSecret) {
      return c.text("inbound shared secret not configured", 401)
    }
    const headerInboundSecret = c.req.header("x-inbound-secret") ?? ""
    if (headerInboundSecret.trim() !== expectedInboundSecret) {
      return c.text("invalid inbound secret", 401)
    }
    const body = (await c.req.json().catch(() => null)) as null | {
      apiVersion?: string
      fromUserId?: string
      content?: string
      messageId?: string
      projectId?: string
      conversationId?: unknown
    }
    if (
      !body ||
      body.apiVersion !== "v1" ||
      typeof body.fromUserId !== "string" ||
      typeof body.content !== "string"
    ) {
      return c.text("invalid body", 400)
    }
    const env = process.env
    const projectSwitch = await tryWechatInboundCommand({
      wiring,
      fromUserId: body.fromUserId,
      content: body.content,
      env,
      mcpBundle: wiring.mcp,
    })
    if (projectSwitch) {
      const inboundProjectId = resolveWechatInboundProjectId(
        body.fromUserId,
        body.projectId,
        env,
      )
      const normalized = normalizeWechatInbound({
        fromUserId: body.fromUserId,
        content: body.content,
        ...(body.messageId ? { messageId: body.messageId } : {}),
        projectId: inboundProjectId,
        conversationId: body.conversationId,
      })
      if (!normalized.ok) {
        if (normalized.error.kind === "invalid_conversation_id") {
          return c.text(`invalid conversationId: ${normalized.error.reason}`, 400)
        }
        return c.text(normalized.error.reason, 400)
      }
      // B 方向 推 2: capture per-user session snapshot after every bot reply.
      // Slash path passes no runResult → lastRunStatus stays "none".
      // D61 T4 (audit #1 F-09): previously a writeSessionStore failure
      // amplified into a 500 on every wechat slash reply. Wrap the
      // snapshot capture so we still serve the bot's reply.
      try {
        await captureWechatSessionSnapshot({
          wiring,
          userId: normalized.value.subject,
          env,
        })
      } catch (err) {
        // eslint-disable-next-line no-console -- operator log when no logger injected
        console.error("[routes] captureWechatSessionSnapshot failed:", err)
      }
      return c.json(
        {
          conversationId: normalized.value.conversationId,
          turnId: normalized.value.turnId,
          reply: projectSwitch.reply,
          meta: {
            iterations: projectSwitch.iterations,
            toolCalls: projectSwitch.toolCalls,
            finalDecision: projectSwitch.finalDecision,
            traces: projectSwitch.traces,
          },
        },
        201,
      )
    }
    const inboundProjectId = resolveWechatInboundProjectId(body.fromUserId, body.projectId, env)
    // R8.x.3 / R8.x.11 / R8.x.13: Intake normalize → Execution (butler loop).
    const normalized = normalizeWechatInbound({
      fromUserId: body.fromUserId,
      content: body.content,
      ...(body.messageId ? { messageId: body.messageId } : {}),
      projectId: inboundProjectId,
      conversationId: body.conversationId,
    })
    if (!normalized.ok) {
      if (normalized.error.kind === "invalid_conversation_id") {
        return c.text(`invalid conversationId: ${normalized.error.reason}`, 400)
      }
      return c.text(normalized.error.reason, 400)
    }
    const { value } = normalized
    await wiring.eventBridge.appendConversationEvent({
      streamId: value.conversationId,
      eventId: `evt-${Date.now()}-wechat-${body.messageId ?? "no-msgid"}`,
      eventType: "ConversationStarted",
      correlationId: `corr-${Date.now()}-${value.subject}`,
      actor: { kind: "system", id: "wechat-forward" },
      event: {
        _tag: "ConversationStarted",
        projectId: value.projectId,
        content: value.content,
        fromUserId: value.subject,
      },
    })
    const loopResult = isWechatIntakeEnabled(env)
      ? await routeWechatIntake({
          wiring,
          conversationId: value.conversationId,
          content: value.content,
          fromUserId: value.subject,
          projectId: value.projectId,
          idempotencyKey: value.idempotencyKey,
          runTrigger: value.runTrigger,
          env,
          mcpBundle: wiring.mcp,
        })
      : await runButlerLoop({
          wiring,
          conversationId: value.conversationId,
          content: value.content,
          fromUserId: value.subject,
          projectId: value.projectId,
          idempotencyKey: value.idempotencyKey,
          runTrigger: value.runTrigger,
        })
    // B 方向 推 2: prepend "since you were last here" digest when owner
    // returns after a long idle. Slash replies skip this — they are
    // deterministic data views, not LLM prose, and don't need a preamble.
    const { reply, digest: sessionDigest } = maybePrependSessionDigest({
      reply: loopResult.reply,
      userId: value.subject,
      now: Date.now(),
      env,
    })
    const traces = sessionDigest
      ? [...loopResult.traces, "session-open-digest:shown"]
      : loopResult.traces
    // Capture snapshot for the *next* session-open digest computation.
    // D62 T1 (audit #1 F-02): mirror the slash-path fix from D61 T4 F-09 —
    // writeSessionStore failure (disk-full / EACCES) must not 500 the
    // primary inbound reply. Log for operators, return the bot's reply.
    try {
      await captureWechatSessionSnapshot({
        wiring,
        userId: value.subject,
        runResult: {
          traces: loopResult.traces,
          finalDecision: loopResult.finalDecision,
        },
        env,
      })
    } catch (err) {
      // eslint-disable-next-line no-console -- operator log when no logger injected
      console.error("[routes] captureWechatSessionSnapshot (default path) failed:", err)
    }
    return c.json(
      {
        conversationId: value.conversationId,
        turnId: value.turnId,
        reply,
        meta: {
          iterations: loopResult.iterations,
          toolCalls: loopResult.toolCalls,
          finalDecision: loopResult.finalDecision,
          traces,
        },
      },
      201,
    )
  })
  app.post("/v1/channel/inbound", async (c) => {
    if (!isChannelApiEnabled(process.env)) {
      return c.text("channel api disabled", 404)
    }
    // D63 T4 (audit #9 F-09): require per-channel shared secret at the
    // generic channel intake seam. The slack/telegram sibling routes
    // have their own per-channel signature verification (x-slack-signature
    // / X-Telegram-Bot-Api-Secret-Token, post-D62 FAIL-CLOSED). The
    // generic channel intake had only allowlist (now FAIL-CLOSED via
    // channel-config.ts:24), but allowlist is operator config — adding
    // a shared-secret header gives an additional authentication factor.
    // FAIL-CLOSED when env secret is unset.
    const expectedChannelSecret = (
      process.env["BUTLER_V5_CHANNEL_INBOUND_SECRET"] ?? ""
    ).trim()
    if (!expectedChannelSecret) {
      return c.text("channel inbound secret not configured", 401)
    }
    const headerChannelSecret = c.req.header("x-channel-inbound-secret") ?? ""
    if (headerChannelSecret.trim() !== expectedChannelSecret) {
      return c.text("invalid channel inbound secret", 401)
    }
    const body = (await c.req.json().catch(() => null)) as null | {
      apiVersion?: string
      channelId?: string
      fromSubject?: string
      content?: string
      messageId?: string
      conversationId?: unknown
    }
    if (
      !body ||
      body.apiVersion !== "v1" ||
      typeof body.channelId !== "string" ||
      typeof body.fromSubject !== "string" ||
      typeof body.content !== "string"
    ) {
      return c.text("invalid body", 400)
    }
    try {
      const result = await handleChannelInbound({
        wiring,
        channelId: body.channelId,
        fromSubject: body.fromSubject,
        content: body.content,
        ...(body.messageId ? { messageId: body.messageId } : {}),
        conversationId: body.conversationId,
      })
      return c.json(result, 201)
    } catch (err) {
      if (err instanceof ChannelInboundError) {
        return c.text(err.message, err.status as 400 | 403)
      }
      throw err
    }
  })
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
      const token = slackBotToken(process.env)
      if (token) {
        const outbound = await deliverSlackChannelReply({
          token,
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
      const token = telegramBotToken(process.env)
      if (token) {
        const outbound = await deliverTelegramChannelReply({
          token,
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
  app.post("/v1/ws/subscribe", async (c) => {
    // D69 T4 (audit #10 SEC-3): require BUTLER_V5_INBOUND_SHARED_SECRET
    // header — any unauthenticated caller could mint a WS subscribe token
    // bound to any conversationId, enabling real-time IDOR on the WS push
    // channel. Mirrors the /v1/wechat/inbound auth pattern.
    const expectedInboundSecret = (process.env["BUTLER_V5_INBOUND_SHARED_SECRET"] ?? "").trim()
    if (!expectedInboundSecret) {
      return c.text("inbound shared secret not configured", 401)
    }
    const headerInboundSecret = c.req.header("x-inbound-secret") ?? ""
    if (headerInboundSecret.trim() !== expectedInboundSecret) {
      return c.text("invalid inbound secret", 401)
    }
    const body = (await c.req.json().catch(() => null)) as null | {
      apiVersion?: string
      conversationId?: unknown
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
    const issued = issueSubscribeToken(parsedId.value)
    if (!issued) {
      // D63 T4 (audit #9 F-14): token store at cap. Return 503 so the
      // caller knows to retry (after prune on existing tokens).
      return c.text("subscribe token store at capacity", 503)
    }
    return c.json(
      {
        conversationId: parsedId.value,
        token: issued.token,
        expiresAt: new Date(issued.expiresAtMs).toISOString(),
        wsPath: `/v1/ws?token=${encodeURIComponent(issued.token)}`,
      },
      201,
    )
  })
  return app
}

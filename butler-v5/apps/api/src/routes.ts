import type { Hono } from "hono"
import type { Wiring } from "./wiring.js"
import {
  defaultWechatConversationId,
  parseClientConversationId,
} from "./conversation-id.js"
import {
  isChannelApiEnabled,
  isSlackChannelEnabled,
  isTelegramChannelEnabled,
} from "./channel-config.js"
import {
  ChannelInboundError,
  handleChannelInbound,
  parseSlackEventPayload,
  parseTelegramUpdate,
  telegramWebhookAuthorized,
  verifySlackSignature,
} from "./channel-inbound.js"
import {
  deliverSlackChannelReply,
  deliverTelegramChannelReply,
  slackBotToken,
  telegramBotToken,
} from "./channel-outbound.js"
import { resolveTelegramInboundContent } from "./channel-media.js"
import { runButlerLoop } from "./wechat-inbound-butler.js"
import { issueSubscribeToken } from "./ws-subscribe.js"

export function createRoutes(app: Hono, wiring: Wiring) {
  app.get("/healthz", (c) => c.json({ status: "ok", wiring: wiring.version }))
  app.post("/v1/conversations", async (c) => {
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
    // Map wechat forward to ConversationStarted event.
    // Use body.projectId when provided, else fall back to "wechat".
    // R8.x.3: after writing the event, run the full AgentKernel-backed
    // butler loop (state machine + tool execution). The loop always
    // returns a non-empty `reply` — either the model's Respond
    // content or the stub fallback — so the v4 → v5 → v4 contract is
    // preserved regardless of LLM availability, tool failure, or
    // decode error.
    //
    // R8.x.11: optional client-supplied conversationId lets WS
    // clients subscribe before this HTTP handler returns.
    // R8.x.13: omitted id is stable per project+user so turns share memory.
    const projectId = body.projectId ?? "wechat"
    const parsedId = parseClientConversationId(body.conversationId)
    if (parsedId.kind === "invalid") {
      return c.text(`invalid conversationId: ${parsedId.reason}`, 400)
    }
    const conversationId =
      parsedId.kind === "valid"
        ? parsedId.value
        : defaultWechatConversationId(projectId, body.fromUserId)
    const turnId = `turn-${Date.now()}`
    await wiring.eventBridge.appendConversationEvent({
      streamId: conversationId,
      eventId: `evt-${Date.now()}-wechat-${body.messageId ?? "no-msgid"}`,
      eventType: "ConversationStarted",
      correlationId: `corr-${Date.now()}-${body.fromUserId}`,
      actor: { kind: "system", id: "wechat-forward" },
      event: {
        _tag: "ConversationStarted",
        projectId,
        content: body.content,
        fromUserId: body.fromUserId,
      },
    })
    const loopResult = await runButlerLoop({
      wiring,
      conversationId,
      content: body.content,
      fromUserId: body.fromUserId,
      projectId,
      idempotencyKey: body.messageId ?? `wechat-${conversationId}-${turnId}`,
    })
    return c.json(
      {
        conversationId,
        turnId,
        reply: loopResult.reply,
        meta: {
          iterations: loopResult.iterations,
          toolCalls: loopResult.toolCalls,
          finalDecision: loopResult.finalDecision,
          traces: loopResult.traces,
        },
      },
      201,
    )
  })
  app.post("/v1/channel/inbound", async (c) => {
    if (!isChannelApiEnabled(process.env)) {
      return c.text("channel api disabled", 404)
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
    const signingSecret = (process.env["BUTLER_V5_SLACK_SIGNING_SECRET"] ?? "").trim()
    const signature = c.req.header("x-slack-signature") ?? ""
    const timestamp = c.req.header("x-slack-request-timestamp") ?? ""
    if (
      signingSecret &&
      !verifySlackSignature(signingSecret, timestamp, signature, rawBody)
    ) {
      return c.text("invalid slack signature", 401)
    }
    let body: unknown
    try {
      body = JSON.parse(rawBody) as unknown
    } catch {
      return c.text("invalid json", 400)
    }
    const parsed = parseSlackEventPayload(body)
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

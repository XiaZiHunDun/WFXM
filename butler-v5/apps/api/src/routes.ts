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
import { isWechatIntakeEnabled, routeWechatIntake } from "./wechat-intake.js"
import { resolveWechatInboundProjectId } from "./wechat-active-project.js"
import { tryWechatInboundCommand } from "./wechat-inbound-commands.js"
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
    return c.json(
      {
        conversationId: value.conversationId,
        turnId: value.turnId,
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

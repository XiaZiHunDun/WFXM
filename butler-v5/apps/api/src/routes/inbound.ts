/**
 * D75 T1 (CQ-005): inbound route handlers extracted from routes.ts.
 *
 * Owns /v1/wechat/inbound (line 103-279 before split) and
 * /v1/channel/inbound (line 280-338). The wechat handler is the
 * largest route in the API (the multi-step intake → butler loop →
 * session-digest → snapshot pipeline); the channel handler is the
 * generic v1 channel intake seam with per-channel secret auth.
 */
import type { Hono } from "hono"
import { normalizeWechatInbound } from "@butler/runtime/intake/index.js"
import type { Wiring } from "../wiring.js"
import { isChannelApiEnabled } from "../channel-config.js"
import { ChannelInboundError, handleChannelInbound } from "../channel-inbound.js"
import { runButlerLoop } from "../wechat-inbound-butler.js"
import { isWechatIntakeEnabled, routeWechatIntake } from "../wechat-intake.js"
import { resolveWechatInboundProjectId } from "../wechat-active-project.js"
import { tryWechatInboundCommand } from "../wechat-inbound-commands.js"
import { captureWechatSessionSnapshot } from "../wechat-session-snapshot.js"
import { maybePrependSessionDigest } from "../wechat-session-digest.js"
import { requireInboundSharedSecret } from "../env-util.js"

export function registerInboundRoutes(app: Hono, wiring: Wiring): void {
  app.post("/v1/wechat/inbound", async (c) => {
    // D63 T4 (audit #9 F-03): require BUTLER_V5_INBOUND_SHARED_SECRET in
    // env + x-inbound-secret header in request. FAIL-CLOSED when env
    // secret is unset (mirror telegram webhook FAIL-CLOSED from D62 T4
    // F-07 — same auth-bypass class). Previously the handler had zero
    // auth, relying on the implicit loopback-only assumption that broke
    // the moment the Hono server bound to 0.0.0.0 (F-06).
    const denied = requireInboundSharedSecret(process.env, c.req.header("x-inbound-secret"))
    if (denied) return denied
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
    // D73 SEC-004: timing-safe compare (was `!==`). Symmetric with the
    // D72-closed Telegram timing-safe path. Length-mismatch short-circuits
    // without throwing (timingSafeEqual throws on unequal length).
    const { safeCompareTrimmedSecrets } = await import("../lib/secure-compare.js")
    if (!safeCompareTrimmedSecrets(expectedChannelSecret, headerChannelSecret)) {
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
}

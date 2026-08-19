import type { Hono } from "hono"
import type { Wiring } from "./wiring.js"
import { parseClientConversationId, defaultWechatConversationId } from "./conversation-id.js"
import { runButlerLoop } from "./wechat-inbound-butler.js"

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
  return app
}

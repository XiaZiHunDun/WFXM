import type { Hono } from "hono"
import type { Wiring } from "./wiring.js"

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
    // The wiring's agent loop will eventually process the event and
    // produce a reply. For MVP, echo back a deterministic placeholder
    // (real v5 butler reply comes via async event consumer later).
    const projectId = body.projectId ?? "wechat"
    const conversationId = `c-${projectId}-${body.fromUserId}-${Date.now()}`
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
    return c.json({
      conversationId,
      turnId,
      reply: `v5 received message from ${body.fromUserId} (project=${projectId}); v5 butler processing is async - this is the MVP stub reply`,
    })
  })
  return app
}

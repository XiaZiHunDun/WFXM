import type { Hono } from "hono"
import type { Wiring } from "./wiring.js"
import { generateLLMReply } from "./wechat-inbound-llm.js"

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
    // R8.x.2: after writing the event, call the configured LLM provider
    // and return its text reply in the response. If no LLM key is set
    // or the LLM call fails, generateLLMReply falls back to the same
    // MVP stub reply that R8.1 returned, so the v4 → v5 → v4 contract
    // is preserved. The async butler loop (R8.x.3) will consume the
    // event for full agent processing.
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
    const reply = await generateLLMReply({
      content: body.content,
      fromUserId: body.fromUserId,
      projectId,
    })
    return c.json({ conversationId, turnId, reply }, 201)
  })
  return app
}

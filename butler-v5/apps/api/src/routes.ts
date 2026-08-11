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
  return app
}

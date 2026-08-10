import type { Hono } from "hono"

interface RoutesConfig {
  readonly eventStore: unknown
}

export function createRoutes(app: Hono, _config: RoutesConfig) {
  app.get("/healthz", (c) => c.json({ status: "ok" }))
  app.post("/v1/conversations", async (c) => {
    const body = (await c.req.json().catch(() => null)) as null | object
    if (!body) return c.text("invalid body", 400)
    return c.json({ conversationId: "c-stub", turnId: "t-stub", ...(body as object) }, 201)
  })
  return app
}

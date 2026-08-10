import { describe, expect, it } from "vitest"
import { Hono } from "hono"
import { createRoutes } from "./routes.js"

describe("HTTP API routes", () => {
  it("GET /healthz returns 200 OK", async () => {
    const app = new Hono()
    createRoutes(app, { eventStore: null as never })
    const res = await app.request("/healthz")
    expect(res.status).toBe(200)
    const body = (await res.json()) as { status: string }
    expect(body.status).toBe("ok")
  })

  it("POST /v1/conversations requires body", async () => {
    const app = new Hono()
    createRoutes(app, { eventStore: null as never })
    const res = await app.request("/v1/conversations", { method: "POST" })
    expect(res.status).toBe(400)
  })
})

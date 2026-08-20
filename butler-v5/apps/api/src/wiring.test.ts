import { describe, expect, it, beforeEach, afterEach, vi } from "vitest"
import { Hono } from "hono"
import { makeWiring, type Wiring } from "./wiring.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import { EventBridge } from "@butler/runtime/bridge.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { createRoutes } from "./routes.js"

vi.mock("./wechat-inbound-butler.js", () => ({
  runButlerLoop: vi.fn(async () => ({
    reply: "stub-reply",
    iterations: 1,
    toolCalls: 0,
    finalDecision: "Respond" as const,
    traces: [],
  })),
}))

describe("v5 wiring", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let wiring: Wiring

  beforeEach(async () => {
    db = await makeTestDb()
    const bridge = new EventBridge({ db: db.db, workerId: "test" })
    const runtimeStore = createRuntimeStore(db.db)
    const runEngine = new RunEngine(runtimeStore)
    wiring = makeWiring({
      bridge,
      workerId: "test",
      runtimeStore,
      runEngine,
      db: db.db,
      backfillConversation: async () => undefined,
    })
  })

  afterEach(async () => {
    await db.close()
  })

  it("exposes eventBridge for Hono routes to consume", () => {
    expect(wiring.eventBridge).toBeDefined()
    expect(typeof wiring.eventBridge.appendConversationEvent).toBe("function")
  })

  it("createRoutes with wiring responds 200 to GET /healthz", async () => {
    const app = new Hono()
    createRoutes(app, wiring)
    const res = await app.request("/healthz")
    expect(res.status).toBe(200)
    const body = (await res.json()) as { status: string; wiring: string }
    expect(body.status).toBe("ok")
    expect(body.wiring).toBe("v5")
  })

  it("createRoutes with wiring responds 201 to POST /v1/conversations", async () => {
    const app = new Hono()
    createRoutes(app, wiring)
    const res = await app.request("/v1/conversations", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        apiVersion: "v1",
        projectId: "p-1",
        toolName: null,
        content: "hello",
      }),
    })
    expect(res.status).toBe(201)
    const body = (await res.json()) as { conversationId: string; turnId: string }
    expect(body.conversationId).toMatch(/^c-p-1-/)
    expect(body.turnId).toMatch(/^turn-/)
  })

  it("createRoutes with wiring responds 400 on invalid body", async () => {
    const app = new Hono()
    createRoutes(app, wiring)
    const res = await app.request("/v1/conversations", { method: "POST" })
    expect(res.status).toBe(400)
  })

  it("R8.x.11: wechat inbound without conversationId generates a server id", async () => {
    const app = new Hono()
    createRoutes(app, wiring)
    const res = await app.request("/v1/wechat/inbound", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        apiVersion: "v1",
        fromUserId: "u-omit",
        content: "hello",
        projectId: "wechat",
      }),
    })
    expect(res.status).toBe(201)
    const body = (await res.json()) as { conversationId: string; reply: string }
    expect(body.conversationId).toBe("c-wechat-u-omit")
    expect(body.reply).toBe("stub-reply")
  })

  it("R8.x.13: two wechat inbounds for the same user reuse one conversationId", async () => {
    const app = new Hono()
    createRoutes(app, wiring)
    const body = {
      apiVersion: "v1",
      fromUserId: "u-memory",
      content: "hello",
      projectId: "wechat",
    }
    const first = await app.request("/v1/wechat/inbound", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    })
    const second = await app.request("/v1/wechat/inbound", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...body, content: "follow up" }),
    })
    const a = (await first.json()) as { conversationId: string }
    const b = (await second.json()) as { conversationId: string }
    expect(a.conversationId).toBe("c-wechat-u-memory")
    expect(b.conversationId).toBe(a.conversationId)
  })

  it("R8.x.11: wechat inbound echoes a valid client conversationId", async () => {
    const app = new Hono()
    createRoutes(app, wiring)
    const clientId = "c-r8x11-presub-client-1"
    const res = await app.request("/v1/wechat/inbound", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        apiVersion: "v1",
        fromUserId: "u-reuse",
        content: "hello",
        projectId: "wechat",
        conversationId: clientId,
      }),
    })
    expect(res.status).toBe(201)
    const body = (await res.json()) as { conversationId: string }
    expect(body.conversationId).toBe(clientId)
    const events = await wiring.eventBridge.loadStream(clientId)
    expect(events.some((e) => e.eventType === "ConversationStarted")).toBe(true)
  })

  it("R8.x.11: wechat inbound rejects an invalid conversationId with 400", async () => {
    const app = new Hono()
    createRoutes(app, wiring)
    const res = await app.request("/v1/wechat/inbound", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        apiVersion: "v1",
        fromUserId: "u-bad",
        content: "hello",
        conversationId: "bad/id",
      }),
    })
    expect(res.status).toBe(400)
    const text = await res.text()
    expect(text).toMatch(/invalid conversationId/)
  })

  it("R8.x.17: POST /v1/ws/subscribe returns a token for a valid conversationId", async () => {
    const app = new Hono()
    createRoutes(app, wiring)
    const res = await app.request("/v1/ws/subscribe", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ apiVersion: "v1", conversationId: "c-owner-live" }),
    })
    expect(res.status).toBe(201)
    const body = (await res.json()) as {
      conversationId: string
      token: string
      expiresAt: string
      wsPath: string
    }
    expect(body.conversationId).toBe("c-owner-live")
    expect(body.token.length).toBeGreaterThan(16)
    expect(body.wsPath).toContain("token=")
    expect(Number.isNaN(Date.parse(body.expiresAt))).toBe(false)
  })

  it("R8.x.17: POST /v1/ws/subscribe rejects a missing conversationId", async () => {
    const app = new Hono()
    createRoutes(app, wiring)
    const res = await app.request("/v1/ws/subscribe", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ apiVersion: "v1" }),
    })
    expect(res.status).toBe(400)
  })
})

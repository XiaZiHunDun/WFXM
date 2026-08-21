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

  it("channel inbound returns 404 when API disabled", async () => {
    const prev = process.env["BUTLER_V5_CHANNEL_API_ENABLED"]
    delete process.env["BUTLER_V5_CHANNEL_API_ENABLED"]
    try {
      const app = new Hono()
      createRoutes(app, wiring)
      const res = await app.request("/v1/channel/inbound", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          apiVersion: "v1",
          channelId: "api",
          fromSubject: "owner-1",
          content: "hello",
        }),
      })
      expect(res.status).toBe(404)
    } finally {
      if (prev === undefined) delete process.env["BUTLER_V5_CHANNEL_API_ENABLED"]
      else process.env["BUTLER_V5_CHANNEL_API_ENABLED"] = prev
    }
  })

  it("channel inbound runs butler loop when enabled", async () => {
    const prev = process.env["BUTLER_V5_CHANNEL_API_ENABLED"]
    process.env["BUTLER_V5_CHANNEL_API_ENABLED"] = "1"
    try {
      const app = new Hono()
      createRoutes(app, wiring)
      const res = await app.request("/v1/channel/inbound", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          apiVersion: "v1",
          channelId: "api",
          fromSubject: "owner-1",
          content: "hello channel",
        }),
      })
      expect(res.status).toBe(201)
      const body = (await res.json()) as { conversationId: string; reply: string; channelId: string }
      expect(body.conversationId).toBe("c-ch-api-owner-1")
      expect(body.channelId).toBe("api")
      expect(body.reply).toBe("stub-reply")
    } finally {
      if (prev === undefined) delete process.env["BUTLER_V5_CHANNEL_API_ENABLED"]
      else process.env["BUTLER_V5_CHANNEL_API_ENABLED"] = prev
    }
  })

  it("slack url_verification returns challenge when enabled", async () => {
    const prev = process.env["BUTLER_V5_SLACK_ENABLED"]
    process.env["BUTLER_V5_SLACK_ENABLED"] = "1"
    try {
      const app = new Hono()
      createRoutes(app, wiring)
      const res = await app.request("/v1/channel/slack/events", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ type: "url_verification", challenge: "challenge-token" }),
      })
      expect(res.status).toBe(200)
      const body = (await res.json()) as { challenge: string }
      expect(body.challenge).toBe("challenge-token")
    } finally {
      if (prev === undefined) delete process.env["BUTLER_V5_SLACK_ENABLED"]
      else process.env["BUTLER_V5_SLACK_ENABLED"] = prev
    }
  })

  it("telegram webhook delivers outbound when bot token is set", async () => {
    const prevEnabled = process.env["BUTLER_V5_TELEGRAM_ENABLED"]
    const prevToken = process.env["BUTLER_V5_TELEGRAM_BOT_TOKEN"]
    process.env["BUTLER_V5_TELEGRAM_ENABLED"] = "1"
    process.env["BUTLER_V5_TELEGRAM_BOT_TOKEN"] = "tg-test-token"
    const fetchMock = vi.fn(async () => Response.json({ ok: true, result: {} }))
    const prevFetch = globalThis.fetch
    globalThis.fetch = fetchMock as typeof fetch
    try {
      const app = new Hono()
      createRoutes(app, wiring)
      const res = await app.request("/v1/channel/telegram/webhook", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          update_id: 1,
          message: { message_id: 7, from: { id: 99 }, text: "telegram hi" },
        }),
      })
      expect(res.status).toBe(200)
      const body = (await res.json()) as {
        ok: boolean
        reply: string
        conversationId: string
        delivered: boolean
      }
      expect(body.conversationId).toBe("c-ch-telegram-99")
      expect(body.reply).toBe("stub-reply")
      expect(body.delivered).toBe(true)
      expect(fetchMock).toHaveBeenCalled()
    } finally {
      globalThis.fetch = prevFetch
      if (prevEnabled === undefined) delete process.env["BUTLER_V5_TELEGRAM_ENABLED"]
      else process.env["BUTLER_V5_TELEGRAM_ENABLED"] = prevEnabled
      if (prevToken === undefined) delete process.env["BUTLER_V5_TELEGRAM_BOT_TOKEN"]
      else process.env["BUTLER_V5_TELEGRAM_BOT_TOKEN"] = prevToken
    }
  })
})

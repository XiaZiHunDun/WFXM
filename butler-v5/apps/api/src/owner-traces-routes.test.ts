import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { Hono } from "hono"
import { EventBridge } from "@butler/persistence/event-bridge.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { resetSharedLocalTracer } from "@butler/runtime/observability/local-tracer.js"
import { createRuntimeStore } from "@butler/persistence"
import { makeTestDb } from "@butler/persistence/testing.js"
import { makeWiring, type Wiring } from "./wiring.js"
import { createOwnerRoutes } from "./owner-routes.js"

describe("owner traces routes", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let wiring: Wiring
  let app: Hono

  beforeEach(async () => {
    resetSharedLocalTracer({ BUTLER_V5_TRACE: "1", BUTLER_V5_OTEL_EXPORTER: "off" })
    db = await makeTestDb()
    const bridge = new EventBridge({ db: db.db, workerId: "w-trace" })
    const runtimeStore = createRuntimeStore(db.db)
    wiring = makeWiring({
      bridge,
      workerId: "w-trace",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      backfillConversation: async () => undefined,
    })
    app = new Hono()
    createOwnerRoutes(app, wiring)
  })

  afterEach(async () => {
    await db.close()
  })

  it("lists run traces after executeInbound", async () => {
    await wiring.runEngine.executeInbound(
      {
        conversationId: "c-trace-1",
        messageId: crypto.randomUUID(),
        subject: "owner",
        content: "hi",
        idempotencyKey: "trace-1",
      },
      async () => ({ ok: true }),
    )
    const res = await app.request("/v1/owner/traces?conversationId=c-trace-1")
    expect(res.status).toBe(200)
    const body = (await res.json()) as {
      enabled: boolean
      items: readonly { kind: string; name: string }[]
    }
    expect(body.enabled).toBe(true)
    expect(body.items.some((e) => e.kind === "run" && e.name === "start")).toBe(true)
    expect(body.items.some((e) => e.kind === "run" && e.name === "finish")).toBe(true)
  })
})

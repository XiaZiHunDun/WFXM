import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { Hono } from "hono"
import { EventBridge } from "@butler/persistence/event-bridge.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { createRuntimeStore } from "@butler/persistence"
import { makeTestDb } from "@butler/persistence/testing.js"
import { makeWiring, type Wiring } from "./wiring.js"
import { registerTracesProceduresTasksRoutes } from "./owner-routes/traces-procedures-tasks.js"

describe("GET /v1/owner/diagnostics", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let app: Hono

  beforeEach(async () => {
    db = await makeTestDb()
    const runtimeStore = createRuntimeStore(db.db)
    const wiring: Wiring = makeWiring({
      bridge: new EventBridge({ db: db.db, workerId: "w-owner-diag" }),
      workerId: "w-owner-diag",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      backfillConversation: async () => undefined,
    })
    app = new Hono()
    registerTracesProceduresTasksRoutes(app, wiring)
  })

  afterEach(async () => {
    await db.close()
  })

  it("returns checks and trace config for the loopback owner", async () => {
    const res = await app.request("/v1/owner/diagnostics")
    expect(res.status).toBe(200)
    const body = (await res.json()) as {
      status: string
      wiring: string
      checks: Record<string, unknown>
      trace: { retention_days: number; max_rows: number; enabled: boolean }
    }
    expect(body.status).toBe("ok")
    expect(body.wiring).toBe("v5")
    expect(body.checks["db"]).toBeDefined()
    expect(body.checks["outbox"]).toBeDefined()
    expect(body.trace.enabled).toBe(true)
    expect(body.trace.retention_days).toBe(30)
    expect(body.trace.max_rows).toBe(200000)
  })

  it("rejects requests arriving through a proxy header", async () => {
    const res = await app.request("/v1/owner/diagnostics", {
      headers: { "x-forwarded-for": "203.0.113.9" },
    })
    expect(res.status).toBe(401)
  })
})

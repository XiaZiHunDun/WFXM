import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { Hono } from "hono"
import { createOwnerRoutes } from "./owner-routes.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { EventBridge } from "@butler/runtime/bridge.js"
import { makeWiring } from "./wiring.js"

describe("owner routes", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  const prevToken = process.env["BUTLER_V5_OWNER_TOKEN"]

  beforeEach(async () => {
    process.env["BUTLER_V5_OWNER_TOKEN"] = "test-owner-token"
    db = await makeTestDb()
  })

  afterEach(async () => {
    if (prevToken === undefined) delete process.env["BUTLER_V5_OWNER_TOKEN"]
    else process.env["BUTLER_V5_OWNER_TOKEN"] = prevToken
    await db.close()
  })

  it("rejects unauthorized approval listing", async () => {
    const bridge = new EventBridge({ db: db.db, workerId: "test" })
    const wiring = makeWiring({
      bridge,
      adapters: {} as never,
      workerId: "test",
      runtimeStore: createRuntimeStore(db.db),
      runEngine: new RunEngine(createRuntimeStore(db.db)),
      db: db.db,
      backfillConversation: async () => undefined,
    })
    const app = new Hono()
    createOwnerRoutes(app, wiring)
    const res = await app.request("/v1/owner/approvals")
    expect(res.status).toBe(401)
  })

  it("lists waiting approval steps for authorized owner", async () => {
    const bridge = new EventBridge({ db: db.db, workerId: "test" })
    const wiring = makeWiring({
      bridge,
      adapters: {} as never,
      workerId: "test",
      runtimeStore: createRuntimeStore(db.db),
      runEngine: new RunEngine(createRuntimeStore(db.db)),
      db: db.db,
      backfillConversation: async () => undefined,
    })
    const app = new Hono()
    createOwnerRoutes(app, wiring)
    const res = await app.request("/v1/owner/approvals", {
      headers: { authorization: "Bearer test-owner-token" },
    })
    expect(res.status).toBe(200)
    const body = (await res.json()) as { items: unknown[] }
    expect(Array.isArray(body.items)).toBe(true)
  })
})

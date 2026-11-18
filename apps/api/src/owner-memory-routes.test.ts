import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { Hono } from "hono"
import { EventBridge } from "@butler/persistence/event-bridge.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { createDurableMemoryRecord } from "@butler/domain/knowledge/durable-memory.js"
import { createDurableMemoryStore, createRuntimeStore } from "@butler/persistence"
import { makeTestDb } from "@butler/persistence/testing.js"
import { makeWiring, type Wiring } from "./wiring.js"
import { createOwnerRoutes } from "./owner-routes.js"
import { loadDurableMemorySystemPrefix } from "./durable-memory-inject.js"

describe("owner durable memory routes", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let wiring: Wiring
  let app: Hono

  beforeEach(async () => {
    db = await makeTestDb()
    const bridge = new EventBridge({ db: db.db, workerId: "w-mem" })
    const runtimeStore = createRuntimeStore(db.db)
    const durableMemoryStore = createDurableMemoryStore(db.db)
    wiring = makeWiring({
      bridge,
      workerId: "w-mem",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      durableMemoryStore,
      backfillConversation: async () => undefined,
    })
    app = new Hono()
    createOwnerRoutes(app, wiring)
  })

  afterEach(async () => {
    await db.close()
  })

  it("creates lists and deletes memories", async () => {
    const createRes = await app.request("/v1/owner/memories", {
      method: "POST",
      headers: {
        "content-type": "application/json",
      },
      body: JSON.stringify({
        subject: "owner",
        content: "喜欢简短中文回复",
        sourceKind: "owner",
      }),
    })
    expect(createRes.status).toBe(200)
    const created = (await createRes.json()) as {
      ok: boolean
      item: { id: string; status: string }
    }
    expect(created.ok).toBe(true)
    expect(created.item.status).toBe("confirmed")

    const listRes = await app.request("/v1/owner/memories?subject=owner")
    const listed = (await listRes.json()) as { items: unknown[] }
    expect(listed.items).toHaveLength(1)

    const delRes = await app.request(`/v1/owner/memories/${created.item.id}`, {
      method: "DELETE",
    })
    expect(delRes.status).toBe(200)
  })

  it("injects confirmed memories when env enabled", async () => {
    const created = createDurableMemoryRecord({
      subject: "owner",
      content: "时区上海",
      sourceKind: "owner",
      nowMs: Date.now(),
    })
    expect(created.ok).toBe(true)
    if (!created.ok) return
    const store = wiring.durableMemoryStore
    expect(store).not.toBeNull()
    if (!store) return
    await store.create(created.value)

    expect(
      await loadDurableMemorySystemPrefix({
        store,
        subject: "owner",
        query: "时区",
        env: {},
      }),
    ).toBeNull()

    const prefix = await loadDurableMemorySystemPrefix({
      store,
      subject: "owner",
      query: "时区",
      env: { BUTLER_V5_DURABLE_MEMORY: "1" },
    })
    expect(prefix).toContain("Durable Memory")
    expect(prefix).toContain("时区上海")
  })
})

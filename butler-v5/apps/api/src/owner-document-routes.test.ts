import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { Hono } from "hono"
import { EventBridge } from "@butler/runtime/bridge.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import {
  createDocumentStore,
  createDurableMemoryStore,
  createRuntimeStore,
} from "@butler/persistence"
import { makeTestDb } from "@butler/persistence/testing.js"
import { makeWiring, type Wiring } from "./wiring.js"
import { createOwnerRoutes } from "./owner-routes.js"

describe("owner document ingest routes", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let wiring: Wiring
  let app: Hono

  beforeEach(async () => {
    db = await makeTestDb()
    const bridge = new EventBridge({ db: db.db, workerId: "w-doc" })
    const runtimeStore = createRuntimeStore(db.db)
    wiring = makeWiring({
      bridge,
      workerId: "w-doc",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      durableMemoryStore: createDurableMemoryStore(db.db),
      documentStore: createDocumentStore(db.db),
      backfillConversation: async () => undefined,
    })
    app = new Hono()
    createOwnerRoutes(app, wiring)
  })

  afterEach(async () => {
    await db.close()
  })

  it("ingests markdown, promotes memory, and cascades delete", async () => {
    const createRes = await app.request("/v1/owner/documents", {
      method: "POST",
      headers: {
        "content-type": "application/json",
      },
      body: JSON.stringify({
        subject: "owner",
        title: "部署手册",
        format: "markdown",
        text: "# Deploy\n先跑 pnpm test",
      }),
    })
    expect(createRes.status).toBe(200)
    const created = (await createRes.json()) as {
      ok: boolean
      item: { id: string; format: string }
    }
    expect(created.ok).toBe(true)
    expect(created.item.format).toBe("markdown")

    const promoteRes = await app.request(
      `/v1/owner/documents/${created.item.id}/promote-memory`,
      {
        method: "POST",
        headers: {
          authorization: "Bearer test-owner-token",
          "content-type": "application/json",
        },
        body: JSON.stringify({}),
      },
    )
    expect(promoteRes.status).toBe(200)
    const promoted = (await promoteRes.json()) as {
      ok: boolean
      item: { status: string; sourceKind: string }
    }
    expect(promoted.ok).toBe(true)
    expect(promoted.item.sourceKind).toBe("document")
    expect(promoted.item.status).toBe("candidate")

    const delRes = await app.request(`/v1/owner/documents/${created.item.id}`, {
      method: "DELETE",
    })
    const deleted = (await delRes.json()) as { ok: boolean; cascadedMemories: number }
    expect(deleted.ok).toBe(true)
    expect(deleted.cascadedMemories).toBe(1)
  })

  it("rejects empty pdf without pre-extracted text", async () => {
    const res = await app.request("/v1/owner/documents", {
      method: "POST",
      headers: {
        "content-type": "application/json",
      },
      body: JSON.stringify({
        title: "scan.pdf",
        format: "pdf",
        text: "",
      }),
    })
    expect(res.status).toBe(400)
  })
})

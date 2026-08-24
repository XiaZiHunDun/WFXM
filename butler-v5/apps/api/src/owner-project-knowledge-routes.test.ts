import { describe, expect, it } from "vitest"
import { Hono } from "hono"
import { EventBridge } from "@butler/runtime/bridge.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { ingestDocumentRecord } from "@butler/domain/knowledge/document-ingest.js"
import {
  createDocumentStore,
  createDurableMemoryStore,
  createProjectKnowledgeStore,
  createRuntimeStore,
} from "@butler/persistence"
import { makeTestDb } from "@butler/persistence/testing.js"
import { makeWiring } from "./wiring.js"
import { createOwnerRoutes } from "./owner-routes.js"

describe("owner project knowledge routes", () => {
  it("adds, lists, promotes from document, and deletes project knowledge", async () => {
    const db = await makeTestDb()
    const bridge = new EventBridge({ db: db.db, workerId: "w-pk" })
    const runtimeStore = createRuntimeStore(db.db)
    const wiring = makeWiring({
      bridge,
      workerId: "w-pk",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      backfillConversation: async () => undefined,
      durableMemoryStore: createDurableMemoryStore(db.db),
      documentStore: createDocumentStore(db.db),
      projectKnowledgeStore: createProjectKnowledgeStore(db.db),
    })
    const app = new Hono()
    createOwnerRoutes(app, wiring)
    const headers = { "content-type": "application/json" }

    const addRes = await app.request("/v1/owner/project-knowledge", {
      method: "POST",
      headers,
      body: JSON.stringify({
        projectId: "WFXM",
        title: "MCP note",
        kind: "manual_note",
        text: "Use manifest for MCP multi-server",
      }),
    })
    expect(addRes.status).toBe(200)
    const added = (await addRes.json()) as { ok: boolean; item: { id: string } }
    expect(added.ok).toBe(true)

    const listRes = await app.request("/v1/owner/project-knowledge?projectId=WFXM")
    expect(listRes.status).toBe(200)
    const listed = (await listRes.json()) as { items: readonly { id: string }[] }
    expect(listed.items.some((i) => i.id === added.item.id)).toBe(true)

    const docCreated = ingestDocumentRecord({
      subject: "owner",
      title: "Spec",
      format: "markdown",
      text: "Project knowledge MVP",
    })
    if (!docCreated.ok) throw new Error(docCreated.reason)
    const documentStore = wiring.documentStore
    if (!documentStore) throw new Error("documentStore missing")
    const doc = await documentStore.create(docCreated.value)
    const promoteRes = await app.request(
      `/v1/owner/documents/${doc.id}/promote-project-knowledge`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({ projectId: "WFXM" }),
      },
    )
    expect(promoteRes.status).toBe(200)

    const delRes = await app.request(`/v1/owner/project-knowledge/${added.item.id}`, {
      method: "DELETE",
    })
    expect(delRes.status).toBe(200)
    await db.close()
  })
})

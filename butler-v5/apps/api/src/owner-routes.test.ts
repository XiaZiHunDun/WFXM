import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { Hono } from "hono"
import { createOwnerRoutes } from "./owner-routes.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { EventBridge } from "@butler/runtime/bridge.js"
import { createWaitingApprovalStep } from "@butler/runtime/approval-runtime.js"
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

  it("approves a waiting step and returns resume outcome", async () => {
    const bridge = new EventBridge({ db: db.db, workerId: "test" })
    const runtimeStore = createRuntimeStore(db.db)
    const wiring = makeWiring({
      bridge,
      workerId: "test",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      backfillConversation: async () => undefined,
    })
    const createdAt = new Date("2026-08-20T00:00:00Z")
    const inbound = await runtimeStore.createConversationWithUserMessage({
      conversationId: "conv-owner-approve",
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "send" },
      triggerSource: "channel",
      idempotencyKey: "owner-approve-msg",
      createdAt,
    })
    const run = await runtimeStore.createRun({
      id: crypto.randomUUID(),
      conversationId: inbound.conversationId,
      parentRunId: null,
      triggerSource: "channel",
      idempotencyKey: "owner-approve-run",
      subject: "owner-1",
      goal: "reply",
      budget: { maxSteps: 5 },
      deadline: null,
      createdAt,
    })
    await runtimeStore.transitionRunStatus(run.id, run.version, "running", createdAt)
    const { stepId } = await createWaitingApprovalStep(runtimeStore, {
      runId: run.id,
      conversationId: inbound.conversationId,
      subject: "owner-1",
      capability: "get_current_time",
      resource: "conv-owner-approve",
      args: {},
      question: "Confirm get_current_time?",
      expiresAtMs: Date.now() + 60_000,
      digest: "d-owner",
      kind: "read",
      risk: "low",
    })
    const app = new Hono()
    createOwnerRoutes(app, wiring)
    const res = await app.request(`/v1/owner/approvals/${stepId}/approve`, {
      method: "POST",
      headers: {
        authorization: "Bearer test-owner-token",
        "content-type": "application/json",
      },
      body: JSON.stringify({ subject: "owner-1" }),
    })
    expect(res.status).toBe(200)
    const body = (await res.json()) as {
      ok: boolean
      output?: string
      trigger?: { source: string; idempotencyKey: string }
    }
    expect(body.ok).toBe(true)
    expect(body.output).toBeTruthy()
    expect(body.trigger).toEqual({
      source: "api",
      idempotencyKey: `owner-approve-${stepId}`,
    })
    const updatedRun = await runtimeStore.getRun(run.id)
    expect(updatedRun?.status).toBe("succeeded")
  })
})

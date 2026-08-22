import { describe, expect, it, beforeEach, afterEach, vi } from "vitest"
import { Hono } from "hono"
import { createOwnerRoutes } from "./owner-routes.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { EventBridge } from "@butler/runtime/bridge.js"
import { createWaitingApprovalStep } from "@butler/runtime/approval-runtime.js"
import { makeWiring } from "./wiring.js"
import * as ownerAuth from "./owner-auth.js"

describe("owner routes", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>

  beforeEach(async () => {
    db = await makeTestDb()
  })

  afterEach(async () => {
    vi.restoreAllMocks()
    await db.close()
  })

  it("rejects non-loopback approval listing", async () => {
    vi.spyOn(ownerAuth, "ownerAuthorized").mockReturnValue(false)
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

  it("lists conversations by projectId for loopback client", async () => {
    const runtimeStore = createRuntimeStore(db.db)
    await runtimeStore.createConversationWithUserMessage({
      conversationId: "c-proj-x-owner",
      messageId: crypto.randomUUID(),
      subject: "owner",
      content: { text: "hi" },
      triggerSource: "channel",
      idempotencyKey: "owner-conv-1",
      createdAt: new Date(),
      projectId: "proj-x",
    })
    const bridge = new EventBridge({ db: db.db, workerId: "test" })
    const wiring = makeWiring({
      bridge,
      workerId: "test",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      backfillConversation: async () => undefined,
    })
    const app = new Hono()
    createOwnerRoutes(app, wiring)
    const res = await app.request("/v1/owner/conversations?projectId=proj-x")
    expect(res.status).toBe(200)
    const body = (await res.json()) as { items: { id: string }[] }
    expect(body.items.map((i) => i.id)).toContain("c-proj-x-owner")
  })

  it("lists messages for a conversation", async () => {
    const runtimeStore = createRuntimeStore(db.db)
    const conversationId = "c-WFXM-msg-list"
    await runtimeStore.createConversationWithUserMessage({
      conversationId,
      messageId: crypto.randomUUID(),
      subject: "owner",
      content: { text: "one" },
      triggerSource: "channel",
      idempotencyKey: "msg-list-1",
      createdAt: new Date(),
      projectId: "WFXM",
    })
    await runtimeStore.appendMessage({
      messageId: crypto.randomUUID(),
      conversationId,
      role: "assistant",
      content: { text: "two" },
      triggerSource: "channel",
      idempotencyKey: null,
      createdAt: new Date(),
    })
    const bridge = new EventBridge({ db: db.db, workerId: "test" })
    const wiring = makeWiring({
      bridge,
      workerId: "test",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      backfillConversation: async () => undefined,
    })
    const app = new Hono()
    createOwnerRoutes(app, wiring)
    const res = await app.request(
      `/v1/owner/conversations/${encodeURIComponent(conversationId)}/messages`,
    )
    expect(res.status).toBe(200)
    const body = (await res.json()) as { items: { role: string }[] }
    expect(body.items.map((m) => m.role)).toEqual(["user", "assistant"])
  })

  it("runs one schedule tick when enabled", async () => {
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
    const app = new Hono()
    createOwnerRoutes(app, wiring)
    const prev = process.env["BUTLER_V5_SCHEDULE_ENABLED"]
    process.env["BUTLER_V5_SCHEDULE_ENABLED"] = "1"
    process.env["BUTLER_V5_SCHEDULE_JOBS"] = JSON.stringify([
      {
        id: "smoke-job",
        everyMs: 60_000,
        goal: "quiet ok",
        cooldownMs: 0,
        maxSteps: 2,
        deadlineMs: 30_000,
        quietSuccess: true,
        enabled: true,
      },
    ])
    try {
      const res = await app.request("/v1/owner/schedule/tick", { method: "POST" })
      expect(res.status).toBe(200)
      const body = (await res.json()) as { ok: boolean; stats: { fired: number } }
      expect(body.ok).toBe(true)
      expect(body.stats.fired).toBeGreaterThanOrEqual(0)
    } finally {
      if (prev === undefined) delete process.env["BUTLER_V5_SCHEDULE_ENABLED"]
      else process.env["BUTLER_V5_SCHEDULE_ENABLED"] = prev
      delete process.env["BUTLER_V5_SCHEDULE_JOBS"]
    }
  })

  it("lists waiting approval steps for loopback client", async () => {
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
      headers: { "content-type": "application/json" },
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

  it("approves run_command with networkAllowlist Grant (P2b)", async () => {
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
      conversationId: "conv-owner-allowlist",
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "pnpm install" },
      triggerSource: "channel",
      idempotencyKey: "owner-allowlist-msg",
      createdAt,
    })
    const run = await runtimeStore.createRun({
      id: crypto.randomUUID(),
      conversationId: inbound.conversationId,
      parentRunId: null,
      triggerSource: "channel",
      idempotencyKey: "owner-allowlist-run",
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
      capability: "run_command",
      resource: "pnpm install",
      args: { argv: ["pnpm", "install"] },
      question: "Confirm run_command?",
      expiresAtMs: Date.now() + 60_000,
      digest: "run_command:pnpm:allowlist",
      kind: "command",
      risk: "high",
    })
    const app = new Hono()
    createOwnerRoutes(app, wiring)
    const res = await app.request(`/v1/owner/approvals/${stepId}/approve`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        subject: "owner-1",
        networkAllowlist: ["registry.npmjs.org:443"],
      }),
    })
    expect(res.status).toBe(200)
    const body = (await res.json()) as {
      ok: boolean
      grant?: { sandboxProfile?: string; networkAllowlist?: string[] }
      reason?: string
    }
    expect(body.grant?.sandboxProfile).toBe("workspace-write-network-allowlist")
    expect(body.grant?.networkAllowlist).toEqual(["registry.npmjs.org:443"])
    const grant = await runtimeStore.findActiveGrant({
      runId: run.id,
      subject: "owner-1",
      capability: "run_command",
      now: new Date(),
    })
    expect(grant?.networkAllowlist).toEqual(["registry.npmjs.org:443"])
  })

  it("cancels an active run via Owner API", async () => {
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
      conversationId: "conv-owner-cancel",
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "hi" },
      triggerSource: "channel",
      idempotencyKey: "owner-cancel-msg",
      createdAt,
    })
    const run = await runtimeStore.createRun({
      id: crypto.randomUUID(),
      conversationId: inbound.conversationId,
      parentRunId: null,
      triggerSource: "channel",
      idempotencyKey: "owner-cancel-run",
      subject: "owner-1",
      goal: "reply",
      budget: { maxSteps: 5 },
      deadline: null,
      createdAt,
    })
    await runtimeStore.transitionRunStatus(run.id, run.version, "running", createdAt)
    const app = new Hono()
    createOwnerRoutes(app, wiring)
    const res = await app.request(`/v1/owner/runs/${run.id}/cancel`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ subject: "owner-1", reason: "test cancel" }),
    })
    expect(res.status).toBe(200)
    const body = (await res.json()) as { ok: boolean; status: string }
    expect(body.ok).toBe(true)
    expect(body.status).toBe("cancelled")
    const updated = await runtimeStore.getRun(run.id)
    expect(updated?.status).toBe("cancelled")
  })

  it("expires overdue runs via Owner API", async () => {
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
      conversationId: "conv-owner-expire",
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "hi" },
      triggerSource: "channel",
      idempotencyKey: "owner-expire-msg",
      createdAt,
    })
    const run = await runtimeStore.createRun({
      id: crypto.randomUUID(),
      conversationId: inbound.conversationId,
      parentRunId: null,
      triggerSource: "channel",
      idempotencyKey: "owner-expire-run",
      subject: "owner-1",
      goal: "reply",
      budget: { maxSteps: 5 },
      deadline: new Date("2026-08-19T00:00:00Z"),
      createdAt,
    })
    await runtimeStore.transitionRunStatus(run.id, run.version, "running", createdAt)
    const app = new Hono()
    createOwnerRoutes(app, wiring)
    const res = await app.request(`/v1/owner/runs/expire-overdue`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ subject: "owner-1" }),
    })
    expect(res.status).toBe(200)
    const body = (await res.json()) as { ok: boolean; count: number; runIds: string[] }
    expect(body.ok).toBe(true)
    expect(body.count).toBeGreaterThanOrEqual(1)
    expect(body.runIds).toContain(run.id)
    const updated = await runtimeStore.getRun(run.id)
    expect(updated?.status).toBe("expired")
  })
})

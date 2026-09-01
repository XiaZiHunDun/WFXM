import { describe, expect, it, beforeEach, afterEach, vi } from "vitest"
import { Hono } from "hono"
import { createOwnerRoutes } from "./owner-routes.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { EventBridge } from "@butler/persistence/event-bridge.js"
import { createWaitingApprovalStep } from "@butler/runtime/approval-runtime.js"
import { makeWiring } from "./wiring.js"
import * as ownerAuth from "./owner-auth.js"
import { createDurableMemoryStore } from "@butler/persistence/durable-memory-store.js"
import {
  confirmDurableMemory,
  createDurableMemoryRecord,
  rejectDurableMemory,
} from "@butler/domain/knowledge/durable-memory.js"

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

  it("P1 acceptance: owner approvals list does not leak pending task args", async () => {
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
    const secret = "SK-abcd-1234-sensitive"
    const inbound = await runtimeStore.createConversationWithUserMessage({
      conversationId: "conv-owner-leak",
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "deploy" },
      triggerSource: "channel",
      idempotencyKey: "owner-leak-msg",
      createdAt,
    })
    const run = await runtimeStore.createRun({
      id: crypto.randomUUID(),
      conversationId: inbound.conversationId,
      parentRunId: null,
      triggerSource: "channel",
      idempotencyKey: "owner-leak-run",
      subject: "owner-1",
      goal: "reply",
      budget: { maxSteps: 5 },
      deadline: null,
      createdAt,
    })
    await runtimeStore.transitionRunStatus(run.id, run.version, "running", createdAt)
    await createWaitingApprovalStep(runtimeStore, {
      runId: run.id,
      conversationId: inbound.conversationId,
      subject: "owner-1",
      capability: "run_command",
      resource: "deploy",
      args: { argv: ["deploy"], token: secret },
      question: "Confirm run_command?",
      expiresAtMs: Date.now() + 60_000,
      digest: "run_command:deploy",
      kind: "command",
      risk: "high",
    })
    const app = new Hono()
    createOwnerRoutes(app, wiring)
    const res = await app.request("/v1/owner/approvals")
    expect(res.status).toBe(200)
    const body = (await res.json()) as { items: (Record<string, unknown> | null)[] }
    expect(body.items).toHaveLength(1)
    const item = JSON.stringify(body.items[0])
    // Sensitive tool args must not be surfaced on the Owner list.
    expect(item).not.toContain(secret)
    expect(item).not.toContain("argv")
    // But the fields needed to approve are present.
    expect(item).toContain("run_command")
    expect(item).toContain("run_command:deploy")
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

  it("returns MCP status and revokes server grants via Owner API", async () => {
    const runtimeStore = createRuntimeStore(db.db)
    const now = new Date()
    const inbound = await runtimeStore.createConversationWithUserMessage({
      conversationId: crypto.randomUUID(),
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "hi" },
      triggerSource: "channel",
      idempotencyKey: "mcp-owner",
      createdAt: now,
    })
    const run = await runtimeStore.createRun({
      id: crypto.randomUUID(),
      conversationId: inbound.conversationId,
      parentRunId: null,
      triggerSource: "channel",
      idempotencyKey: "mcp-run",
      subject: "owner-1",
      goal: "test",
      budget: {},
      deadline: null,
      createdAt: now,
    })
    await runtimeStore.createScopedGrant({
      grantId: crypto.randomUUID(),
      runId: run.id,
      subject: "owner-1",
      scope: {
        capabilities: ["mcp_search"],
        digest: "d1",
        network: "allow",
        mcp: { serverId: "demo-server", toolName: "search" },
      },
      remainingUses: 1,
      expiresAt: new Date(Date.now() + 3600_000),
      createdAt: now,
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
    const statusRes = await app.request("/v1/owner/mcp/status")
    expect(statusRes.status).toBe(200)
    const status = (await statusRes.json()) as { activeGrants: number; mode: string }
    expect(status.mode).toBe("off")
    expect(status.activeGrants).toBe(0)
    const revokeRes = await app.request("/v1/owner/mcp/servers/demo-server/revoke-grants", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ subject: "owner" }),
    })
    expect(revokeRes.status).toBe(200)
    const revoked = (await revokeRes.json()) as { ok: boolean; revoked: number }
    expect(revoked.ok).toBe(true)
    expect(revoked.revoked).toBe(1)
  })
})

describe("GET /v1/owner/memories pagination + total", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let store: ReturnType<typeof createDurableMemoryStore>
  let app: Hono

  beforeEach(async () => {
    db = await makeTestDb()
    store = createDurableMemoryStore(db.db)
    const runtimeStore = createRuntimeStore(db.db)
    const bridge = new EventBridge({ db: db.db, workerId: "test" })
    const wiring = makeWiring({
      bridge,
      workerId: "test",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      backfillConversation: async () => undefined,
      durableMemoryStore: store,
    })
    app = new Hono()
    createOwnerRoutes(app, wiring)
  })

  afterEach(async () => {
    vi.restoreAllMocks()
    await db.close()
  })

  async function seedCandidate(content: string): Promise<string> {
    const made = createDurableMemoryRecord({
      subject: "owner",
      content,
      sourceKind: "owner",
      status: "candidate",
    })
    if (!made.ok) throw new Error(made.reason)
    const saved = await store.create(made.value)
    return saved.id
  }

  it("returns items + total + hasMore=false when all fit on one page", async () => {
    await seedCandidate("a")
    await seedCandidate("b")
    const res = await app.request("/v1/owner/memories?status=candidate&limit=20&offset=0")
    expect(res.status).toBe(200)
    const body = (await res.json()) as { items: unknown[]; total: number; hasMore: boolean }
    expect(body.items).toHaveLength(2)
    expect(body.total).toBe(2)
    expect(body.hasMore).toBe(false)
  })

  it("returns hasMore=true when more records exist after offset+limit", async () => {
    await seedCandidate("a")
    await seedCandidate("b")
    await seedCandidate("c")
    const res = await app.request("/v1/owner/memories?status=candidate&limit=2&offset=0")
    expect(res.status).toBe(200)
    const body = (await res.json()) as { items: unknown[]; total: number; hasMore: boolean }
    expect(body.items).toHaveLength(2)
    expect(body.total).toBe(3)
    expect(body.hasMore).toBe(true)
  })

  it("rejects invalid status with 400", async () => {
    const res = await app.request("/v1/owner/memories?status=foo")
    expect(res.status).toBe(400)
    const body = (await res.json()) as { ok: boolean; reason: string }
    expect(body).toMatchObject({ ok: false, reason: expect.any(String) })
  })

  it("accepts status=expired (G1: owner can query expired history)", async () => {
    const res = await app.request("/v1/owner/memories?status=expired&limit=20")
    expect(res.status).toBe(200)
  })

  it("rejects limit>100 with 400", async () => {
    const res = await app.request("/v1/owner/memories?limit=200")
    expect(res.status).toBe(400)
    const body = (await res.json()) as { ok: boolean; reason: string }
    expect(body).toMatchObject({ ok: false, reason: expect.any(String) })
  })

  it("rejects negative offset with 400", async () => {
    const res = await app.request("/v1/owner/memories?offset=-1")
    expect(res.status).toBe(400)
    const body = (await res.json()) as { ok: boolean; reason: string }
    expect(body).toMatchObject({ ok: false, reason: expect.any(String) })
  })

  it("rejects limit=0 with 400 (lower bound)", async () => {
    const res = await app.request("/v1/owner/memories?limit=0")
    expect(res.status).toBe(400)
  })

  it("accepts limit=100 (upper bound) with 200", async () => {
    await seedCandidate("a")
    const res = await app.request("/v1/owner/memories?limit=100")
    expect(res.status).toBe(200)
    const body = (await res.json()) as { items: unknown[]; limit?: number }
    expect(body.items.length).toBeGreaterThanOrEqual(1)
  })

  it("rejects non-numeric limit (NaN path) with 400", async () => {
    const res = await app.request("/v1/owner/memories?limit=abc")
    expect(res.status).toBe(400)
  })

  it("offset beyond total returns empty items + hasMore=false", async () => {
    await seedCandidate("a")
    const res = await app.request("/v1/owner/memories?status=candidate&offset=999999")
    expect(res.status).toBe(200)
    const body = (await res.json()) as { items: unknown[]; total: number; hasMore: boolean }
    expect(body.items).toHaveLength(0)
    expect(body.total).toBe(1)
    expect(body.hasMore).toBe(false)
  })

  it("omitting status returns all-status unfiltered list", async () => {
    await seedCandidate("candidate-only")
    const conf = createDurableMemoryRecord({
      subject: "owner",
      content: "confirmed",
      sourceKind: "owner",
      status: "confirmed",
    })
    if (!conf.ok) throw new Error(conf.reason)
    await store.create(conf.value)
    const res = await app.request("/v1/owner/memories")
    expect(res.status).toBe(200)
    const body = (await res.json()) as { items: { status: string }[]; total: number }
    expect(body.total).toBe(2)
    const statuses = new Set(body.items.map((it) => it.status))
    expect(statuses.has("candidate")).toBe(true)
    expect(statuses.has("confirmed")).toBe(true)
  })
})

describe("POST /v1/owner/memories/confirm-batch + /reject-batch", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let store: ReturnType<typeof createDurableMemoryStore>
  let app: Hono

  beforeEach(async () => {
    db = await makeTestDb()
    store = createDurableMemoryStore(db.db)
    const runtimeStore = createRuntimeStore(db.db)
    const bridge = new EventBridge({ db: db.db, workerId: "test" })
    const wiring = makeWiring({
      bridge,
      workerId: "test",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      backfillConversation: async () => undefined,
      durableMemoryStore: store,
    })
    app = new Hono()
    createOwnerRoutes(app, wiring)
  })

  afterEach(async () => {
    vi.restoreAllMocks()
    await db.close()
  })

  async function seedCandidate(content: string): Promise<string> {
    const made = createDurableMemoryRecord({
      subject: "owner",
      content,
      sourceKind: "owner",
      status: "candidate",
    })
    if (!made.ok) throw new Error(made.reason)
    const saved = await store.create(made.value)
    return saved.id
  }

  async function postJSON(path: string, body: unknown): Promise<Response> {
    return app.request(path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    })
  }

  it("confirm-batch confirms all valid candidate ids", async () => {
    const id1 = await seedCandidate("fact-1")
    const id2 = await seedCandidate("fact-2")
    const res = await postJSON("/v1/owner/memories/confirm-batch", { ids: [id1, id2] })
    expect(res.status).toBe(200)
    const body = (await res.json()) as {
      confirmed: string[]
      failed: { id: string; reason: string }[]
    }
    expect([...body.confirmed].sort()).toEqual([id1, id2].sort())
    expect(body.failed).toEqual([])
  })

  it("confirm-batch dedups same id in request", async () => {
    const id1 = await seedCandidate("dup")
    const res = await postJSON("/v1/owner/memories/confirm-batch", { ids: [id1, id1] })
    expect(res.status).toBe(200)
    const body = (await res.json()) as { confirmed: string[]; failed: unknown[] }
    expect(body.confirmed).toEqual([id1])
  })

  it("confirm-batch partial failure returns 200 + failed[]", async () => {
    const id1 = await seedCandidate("ok")
    const res = await postJSON("/v1/owner/memories/confirm-batch", {
      ids: [id1, "missing-id"],
    })
    expect(res.status).toBe(200)
    const body = (await res.json()) as {
      confirmed: string[]
      failed: { id: string; reason: string }[]
    }
    expect(body.confirmed).toEqual([id1])
    expect(body.failed).toEqual([{ id: "missing-id", reason: "not found" }])
  })

  it("confirm-batch rejects already-confirmed candidate", async () => {
    const id1 = await seedCandidate("already")
    const existing = await store.get(id1)
    if (!existing) throw new Error("seed")
    await store.update(confirmDurableMemory(existing, Date.now()))
    const res = await postJSON("/v1/owner/memories/confirm-batch", { ids: [id1] })
    expect(res.status).toBe(200)
    const body = (await res.json()) as {
      confirmed: unknown[]
      failed: { id: string; reason: string }[]
    }
    expect(body.confirmed).toEqual([])
    expect(body.failed).toEqual([{ id: id1, reason: "already confirmed" }])
  })

  it("confirm-batch rejects subject mismatch", async () => {
    const made = createDurableMemoryRecord({
      subject: "other-owner",
      content: "x",
      sourceKind: "owner",
      status: "candidate",
    })
    if (!made.ok) throw new Error(made.reason)
    const saved = await store.create(made.value)
    const res = await postJSON("/v1/owner/memories/confirm-batch", { ids: [saved.id] })
    expect(res.status).toBe(200)
    const body = (await res.json()) as {
      confirmed: unknown[]
      failed: { id: string; reason: string }[]
    }
    expect(body.confirmed).toEqual([])
    expect(body.failed).toEqual([{ id: saved.id, reason: "subject mismatch" }])
  })

  it("confirm-batch rejects empty ids with 400", async () => {
    const res = await postJSON("/v1/owner/memories/confirm-batch", { ids: [] })
    expect(res.status).toBe(400)
    const body = (await res.json()) as { ok: boolean; reason: string }
    expect(body).toMatchObject({ ok: false, reason: expect.any(String) })
  })

  it("confirm-batch rejects >50 ids with 400", async () => {
    const ids = Array.from({ length: 51 }, (_, i) => `id-${i}`)
    const res = await postJSON("/v1/owner/memories/confirm-batch", { ids })
    expect(res.status).toBe(400)
  })

  it("confirm-batch rejects non-string id with 400", async () => {
    const res = await postJSON("/v1/owner/memories/confirm-batch", {
      ids: ["ok", 123],
    })
    expect(res.status).toBe(400)
  })

  it("reject-batch rejects candidate", async () => {
    const id1 = await seedCandidate("to-reject")
    const res = await postJSON("/v1/owner/memories/reject-batch", { ids: [id1] })
    expect(res.status).toBe(200)
    const body = (await res.json()) as { rejected: string[]; failed: unknown[] }
    expect(body.rejected).toEqual([id1])
  })

  it("reject-batch rejects already-rejected candidate", async () => {
    const id1 = await seedCandidate("rej")
    const existing = await store.get(id1)
    if (!existing) throw new Error("seed")
    await store.update(rejectDurableMemory(existing, Date.now()))
    const res = await postJSON("/v1/owner/memories/reject-batch", { ids: [id1] })
    expect(res.status).toBe(200)
    const body = (await res.json()) as {
      rejected: unknown[]
      failed: { id: string; reason: string }[]
    }
    expect(body.rejected).toEqual([])
    expect(body.failed).toEqual([{ id: id1, reason: "already rejected" }])
  })

  it("single-record confirm returns 409 on re-confirm (regression: silent bump)", async () => {
    const id1 = await seedCandidate("re-confirm")
    const first = await app.request(`/v1/owner/memories/${id1}/confirm`, {
      method: "POST",
    })
    expect(first.status).toBe(200)
    const second = await app.request(`/v1/owner/memories/${id1}/confirm`, {
      method: "POST",
    })
    expect(second.status).toBe(409)
    const body = (await second.json()) as { ok: boolean; reason: string }
    expect(body).toEqual({ ok: false, reason: "already confirmed" })
  })

  it("single-record reject returns 409 on re-reject (regression: silent bump)", async () => {
    const id1 = await seedCandidate("re-reject")
    const first = await app.request(`/v1/owner/memories/${id1}/reject`, {
      method: "POST",
    })
    expect(first.status).toBe(200)
    const second = await app.request(`/v1/owner/memories/${id1}/reject`, {
      method: "POST",
    })
    expect(second.status).toBe(409)
    const body = (await second.json()) as { ok: boolean; reason: string }
    expect(body).toEqual({ ok: false, reason: "already rejected" })
  })

  it("single-record confirm returns 409 when status='expired' (G1 terminal guard)", async () => {
    const id1 = await seedCandidate("expired-confirm")
    await store.markExpired([id1])
    const res = await app.request(`/v1/owner/memories/${id1}/confirm`, {
      method: "POST",
    })
    expect(res.status).toBe(409)
    const body = (await res.json()) as { ok: boolean; reason: string }
    expect(body).toEqual({ ok: false, reason: "already expired" })
  })

  it("single-record reject returns 409 when status='expired' (G1 terminal guard)", async () => {
    const id1 = await seedCandidate("expired-reject")
    await store.markExpired([id1])
    const res = await app.request(`/v1/owner/memories/${id1}/reject`, {
      method: "POST",
    })
    expect(res.status).toBe(409)
    const body = (await res.json()) as { ok: boolean; reason: string }
    expect(body).toEqual({ ok: false, reason: "already expired" })
  })

  it("confirm-batch puts expired ids in failed[] (G1 terminal guard, partial failure)", async () => {
    const idCandidate = await seedCandidate("still-candidate")
    const idExpired = await seedCandidate("was-expired")
    await store.markExpired([idExpired])
    const res = await postJSON("/v1/owner/memories/confirm-batch", {
      ids: [idCandidate, idExpired],
    })
    expect(res.status).toBe(200)
    const body = (await res.json()) as {
      confirmed: string[]
      failed: { id: string; reason: string }[]
    }
    expect(body.confirmed).toEqual([idCandidate])
    expect(body.failed).toEqual([{ id: idExpired, reason: "already expired" }])
  })
})

describe("POST /v1/owner/memories G2 dedup guard", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let store: ReturnType<typeof createDurableMemoryStore>
  let app: Hono

  beforeEach(async () => {
    db = await makeTestDb()
    store = createDurableMemoryStore(db.db)
    const runtimeStore = createRuntimeStore(db.db)
    const bridge = new EventBridge({ db: db.db, workerId: "test" })
    const wiring = makeWiring({
      bridge,
      workerId: "test",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      backfillConversation: async () => undefined,
      durableMemoryStore: store,
    })
    app = new Hono()
    createOwnerRoutes(app, wiring)
  })

  afterEach(async () => {
    vi.restoreAllMocks()
    await db.close()
  })

  async function postJSON(path: string, body: unknown): Promise<Response> {
    return app.request(path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    })
  }

  it("returns 409 when dedup hit on identical content (G2)", async () => {
    // Seed a confirmed memory with content "owner prefers tea"
    const made = createDurableMemoryRecord({
      subject: "owner",
      content: "owner prefers tea",
      sourceKind: "owner",
      status: "confirmed",
    })
    if (!made.ok) throw new Error(made.reason)
    const seeded = await store.create(made.value)
    // Attempt to create an identical candidate — should be blocked with 409
    const res = await postJSON("/v1/owner/memories", {
      content: "owner prefers tea",
      subject: "owner",
    })
    expect(res.status).toBe(409)
    const body = (await res.json()) as {
      ok: boolean
      reason: string
      existingMemoryId: string
      similarity: number
      status: string
    }
    expect(body.ok).toBe(false)
    expect(body.reason).toBe("duplicate")
    expect(body.existingMemoryId).toBe(seeded.id)
    expect(body.status).toBe("confirmed")
    // Trigram Jaccard on identical content yields 1.0
    expect(body.similarity).toBeGreaterThanOrEqual(0.85)
  })

  it("force=true bypasses dedup and creates the duplicate (G2)", async () => {
    // Seed a confirmed memory
    const made = createDurableMemoryRecord({
      subject: "owner",
      content: "owner prefers tea",
      sourceKind: "owner",
      status: "confirmed",
    })
    if (!made.ok) throw new Error(made.reason)
    await store.create(made.value)
    // Same content but force=true — should succeed (200, item returned)
    const res = await postJSON("/v1/owner/memories", {
      content: "owner prefers tea",
      subject: "owner",
      force: true,
    })
    expect(res.status).toBe(200)
    const body = (await res.json()) as { ok: boolean; item: { content: string } }
    expect(body.ok).toBe(true)
    expect(body.item.content).toBe("owner prefers tea")
    // Verify both records exist now
    const list = await store.listBySubject({ subject: "owner", limit: 10 })
    const matching = list.filter((m) => m.content === "owner prefers tea")
    expect(matching.length).toBe(2)
  })

  it("below threshold proceeds (similar content but not duplicate) (G2)", async () => {
    // Seed a confirmed memory "owner prefers tea"
    const made = createDurableMemoryRecord({
      subject: "owner",
      content: "owner prefers tea",
      sourceKind: "owner",
      status: "confirmed",
    })
    if (!made.ok) throw new Error(made.reason)
    await store.create(made.value)
    // Post sufficiently different content — should proceed (200)
    const res = await postJSON("/v1/owner/memories", {
      content: "owner likes coffee",
      subject: "owner",
    })
    expect(res.status).toBe(200)
    const body = (await res.json()) as { ok: boolean; item: { content: string } }
    expect(body.ok).toBe(true)
    expect(body.item.content).toBe("owner likes coffee")
  })
})

describe("POST /v1/owner/memories/:memoryId/rollback-auto-promote (G4)", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let store: ReturnType<typeof createDurableMemoryStore>
  let app: Hono

  beforeEach(async () => {
    db = await makeTestDb()
    store = createDurableMemoryStore(db.db)
    const runtimeStore = createRuntimeStore(db.db)
    const bridge = new EventBridge({ db: db.db, workerId: "test" })
    const wiring = makeWiring({
      bridge,
      workerId: "test",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      backfillConversation: async () => undefined,
      durableMemoryStore: store,
    })
    app = new Hono()
    createOwnerRoutes(app, wiring)
    // Freeze route's `new Date()` to 1 min past baseMs (Sept 1 2026, 00:01 UTC).
    // Route constructs records at baseMs (Sept 1 2026 00:00:00 UTC); 1 min
    // past baseMs keeps `now` inside the 7-day window. Prevents time-coupled
    // CI failures once wall clock crosses baseMs + 7d (2026-09-08T00:00:10Z).
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-09-01T00:01:00Z"))
  })

  afterEach(async () => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    await db.close()
  })

  async function postJSON(path: string, body: unknown): Promise<Response> {
    return app.request(path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    })
  }

  it("returns 200 with rolled-back record on valid rollback (sweeper-promoted, within window)", async () => {
    const baseMs = Date.parse("2026-09-01T00:00:00Z")
    const made = createDurableMemoryRecord({
      subject: "owner",
      content: "owner likes tea",
      sourceKind: "owner",
      status: "candidate",
      nowMs: baseMs,
    })
    if (!made.ok) throw new Error(made.reason)
    await store.create(made.value)
    // sweeper promotes at baseMs + 10s
    await store.markAutoPromoted({ ids: [made.value.id], now: new Date(baseMs + 10_000) })

    const res = await postJSON(
      `/v1/owner/memories/${made.value.id}/rollback-auto-promote`,
      { reason: "looks wrong" },
    )
    expect(res.status).toBe(200)
    const body = (await res.json()) as {
      memory: {
        id: string
        status: string
        rolledBackBy: string
        rollbackReason: string | null
      }
    }
    expect(body.memory.id).toBe(made.value.id)
    expect(body.memory.status).toBe("candidate")
    expect(body.memory.rolledBackBy).toBe("owner")
    expect(body.memory.rollbackReason).toBe("looks wrong")

    // Verify DB state: status='candidate', rolledBackBy='owner', promotedBy preserved as 'sweeper'
    const after = await store.get(made.value.id)
    if (!after) throw new Error("record should still exist")
    expect(after.status).toBe("candidate")
    expect(after.promotedBy).toBe("sweeper")
    expect(after.rolledBackBy).toBe("owner")
    expect(after.rollbackReason).toBe("looks wrong")
  })

  it("returns 404 when memoryId does not exist", async () => {
    const res = await postJSON(
      "/v1/owner/memories/nonexistent/rollback-auto-promote",
      { reason: "test" },
    )
    expect(res.status).toBe(404)
    const body = (await res.json()) as { ok: boolean; reason: string }
    expect(body).toEqual({ ok: false, reason: "not found" })
  })

  it("returns 409 not-confirmed when status is 'candidate' (never promoted)", async () => {
    const baseMs = Date.parse("2026-09-01T00:00:00Z")
    const made = createDurableMemoryRecord({
      subject: "owner",
      content: "still a candidate",
      sourceKind: "owner",
      status: "candidate",
      nowMs: baseMs,
    })
    if (!made.ok) throw new Error(made.reason)
    await store.create(made.value)
    // No markAutoPromoted — status remains 'candidate'

    const res = await postJSON(
      `/v1/owner/memories/${made.value.id}/rollback-auto-promote`,
      { reason: "test" },
    )
    expect(res.status).toBe(409)
    const body = (await res.json()) as { ok: boolean; error: string; currentStatus: string }
    expect(body.ok).toBe(false)
    expect(body.error).toBe("not-confirmed")
    expect(body.currentStatus).toBe("candidate")
  })

  it("returns 409 not-auto-promoted when record was owner-confirmed (promotedBy='owner')", async () => {
    const baseMs = Date.parse("2026-09-01T00:00:00Z")
    const made = createDurableMemoryRecord({
      subject: "owner",
      content: "owner confirmed directly",
      sourceKind: "owner",
      status: "confirmed",
      nowMs: baseMs,
    })
    if (!made.ok) throw new Error(made.reason)
    await store.create(made.value)
    // promotedBy is null after createDurableMemoryRecord; owner-confirm path
    // does not set promotedBy. So this exercises the not-auto-promoted branch
    // (promotedBy is not 'sweeper', regardless of whether it's null or 'owner').

    const res = await postJSON(
      `/v1/owner/memories/${made.value.id}/rollback-auto-promote`,
      { reason: "test" },
    )
    expect(res.status).toBe(409)
    const body = (await res.json()) as { ok: boolean; error: string }
    expect(body.ok).toBe(false)
    expect(body.error).toBe("not-auto-promoted")
  })

  it("returns 409 rollback-window-expired when past 7d post-promote window", async () => {
    const baseMs = Date.parse("2026-09-01T00:00:00Z")
    const made = createDurableMemoryRecord({
      subject: "owner",
      content: "sweeper promoted but stale",
      sourceKind: "owner",
      status: "candidate",
      nowMs: baseMs,
    })
    if (!made.ok) throw new Error(made.reason)
    await store.create(made.value)
    // sweeper promoted 8 days ago (well past default 7d rollback window)
    await store.markAutoPromoted({ ids: [made.value.id], now: new Date(baseMs) })

    // Override route's `new Date()` to baseMs + 8d (rolls past 7d window).
    // vi.useFakeTimers() is already set by the describe-level beforeEach.
    vi.setSystemTime(new Date(baseMs + 8 * 24 * 3_600_000))

    const res = await postJSON(
      `/v1/owner/memories/${made.value.id}/rollback-auto-promote`,
      { reason: "too late" },
    )
    expect(res.status).toBe(409)
    const body = (await res.json()) as {
      ok: boolean
      error: string
      currentStatus: string
      promotedBy: string | null
      rollbackDeadline: string | null
    }
    expect(body.ok).toBe(false)
    expect(body.error).toBe("rollback-window-expired")
    expect(body.currentStatus).toBe("confirmed")
    expect(body.promotedBy).toBe("sweeper")
    // promotedAt=baseMs, deadline = baseMs + 7d (in ISO)
    expect(body.rollbackDeadline).toBe(new Date(baseMs + 7 * 24 * 3_600_000).toISOString())
  })

  it("returns 409 with concurrent-modification when store.rollbackAutoPromoted returns null", async () => {
    const baseMs = Date.parse("2026-09-01T00:00:00Z")
    const made = createDurableMemoryRecord({
      subject: "owner",
      content: "race condition target",
      sourceKind: "owner",
      status: "candidate",
      nowMs: baseMs,
    })
    if (!made.ok) throw new Error(made.reason)
    await store.create(made.value)
    // Set up DB state so the validation step passes (status=confirmed,
    // promotedBy=sweeper). We then stub rollbackAutoPromoted to return null
    // to simulate the race window: status/promotedBy changed between route's
    // get and the UPDATE (e.g. another rollback won).
    await store.markAutoPromoted({
      ids: [made.value.id],
      now: new Date(baseMs + 10_000),
    })
    // Stub: simulate concurrent modification by returning null from the
    // persistence adapter's UPDATE.
    vi.spyOn(store, "rollbackAutoPromoted").mockResolvedValue(null)

    const res = await postJSON(
      `/v1/owner/memories/${made.value.id}/rollback-auto-promote`,
      { reason: "test" },
    )
    expect(res.status).toBe(409)
    const body = (await res.json()) as { ok: boolean; error: string }
    expect(body.ok).toBe(false)
    expect(body.error).toBe("concurrent-modification")
  })
})

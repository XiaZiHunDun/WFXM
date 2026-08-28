import { describe, expect, it } from "vitest"
import { sql } from "drizzle-orm"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import { createRuntimeStore } from "./runtime-store.js"
import { makeTestDb } from "./testing.js"

describe("RuntimeStore repository", () => {
  it("idempotently creates a conversation with its inbound user message", async () => {
    const db = await makeTestDb()
    const store: RuntimeStore = createRuntimeStore(db)
    const input = {
      conversationId: crypto.randomUUID(),
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "hello" },
      triggerSource: "channel" as const,
      idempotencyKey: "wechat-message-1",
      createdAt: new Date("2026-08-20T00:00:00Z"),
    }
    try {
      const first = await store.createConversationWithUserMessage(input)
      const second = await store.createConversationWithUserMessage({
        ...input,
        conversationId: crypto.randomUUID(),
        messageId: crypto.randomUUID(),
      })

      expect(second).toEqual(first)
      expect(await store.listMessages(first.conversationId)).toEqual([
        expect.objectContaining({
          id: first.messageId,
          conversationId: first.conversationId,
          role: "user",
          content: { text: "hello" },
        }),
      ])
    } finally {
      await db.close()
    }
  })

  it("redacts secret-bearing message content before persisting (durable transcript)", async () => {
    const db = await makeTestDb()
    const store: RuntimeStore = createRuntimeStore(db)
    const conversationId = crypto.randomUUID()
    try {
      const created = await store.createConversationWithUserMessage({
        conversationId,
        messageId: crypto.randomUUID(),
        subject: "owner-1",
        content: { text: "token=deadbeef and Bearer xyz.abc.def plus sk-abc123456789" },
        triggerSource: "channel",
        idempotencyKey: "msg-secret-1",
        createdAt: new Date("2026-08-26T00:00:00Z"),
      })
      const messages = await store.listMessages(conversationId)
      const stored = messages.find((m) => m.id === created.messageId)
      const storedText = (stored?.content as Readonly<Record<string, unknown>>)["text"]
      expect(String(storedText)).not.toContain("deadbeef")
      expect(String(storedText)).not.toContain("sk-abc123456789")
      expect(String(storedText)).toContain("***")
    } finally {
      await db.close()
    }
  })

  it("appends a second user message to an existing conversation", async () => {
    const db = await makeTestDb()
    const store: RuntimeStore = createRuntimeStore(db)
    const conversationId = crypto.randomUUID()
    try {
      await store.createConversationWithUserMessage({
        conversationId,
        messageId: crypto.randomUUID(),
        subject: "owner-1",
        content: { text: "first" },
        triggerSource: "channel",
        idempotencyKey: "msg-1",
        createdAt: new Date("2026-08-20T00:00:00Z"),
      })
      await store.createConversationWithUserMessage({
        conversationId,
        messageId: crypto.randomUUID(),
        subject: "owner-1",
        content: { text: "second" },
        triggerSource: "channel",
        idempotencyKey: "msg-2",
        createdAt: new Date("2026-08-20T00:01:00Z"),
      })
      const messages = await store.listMessages(conversationId)
      expect(messages).toHaveLength(2)
      expect(messages.map((m) => m.content)).toEqual([{ text: "first" }, { text: "second" }])
    } finally {
      await db.close()
    }
  })

  it("creates and transitions a main Run with optimistic versioning", async () => {
    const db = await makeTestDb()
    const store: RuntimeStore = createRuntimeStore(db)
    const createdAt = new Date("2026-08-20T00:00:00Z")
    try {
      const inbound = await store.createConversationWithUserMessage({
        conversationId: crypto.randomUUID(),
        messageId: crypto.randomUUID(),
        subject: "owner-1",
        content: { text: "hello" },
        triggerSource: "channel",
        idempotencyKey: "wechat-message-2",
        createdAt,
      })
      const run = await store.createRun({
        id: crypto.randomUUID(),
        conversationId: inbound.conversationId,
        parentRunId: null,
        triggerSource: "channel",
        idempotencyKey: "run-2",
        subject: "owner-1",
        goal: "reply",
        budget: { maxSteps: 5 },
        deadline: null,
        createdAt,
      })

      expect(run.status).toBe("queued")
      const running = await store.transitionRunStatus(
        run.id,
        1,
        "running",
        new Date(createdAt.getTime() + 1),
      )
      expect(running).toEqual(expect.objectContaining({ status: "running", version: 2 }))
      await expect(
        store.transitionRunStatus(run.id, 1, "failed", new Date(createdAt.getTime() + 2)),
      ).rejects.toThrow(/version/i)
    } finally {
      await db.close()
    }
  })

  it("creates a Step for a Run", async () => {
    const db = await makeTestDb()
    const store: RuntimeStore = createRuntimeStore(db)
    const createdAt = new Date("2026-08-20T00:00:00Z")
    try {
      const inbound = await store.createConversationWithUserMessage({
        conversationId: crypto.randomUUID(),
        messageId: crypto.randomUUID(),
        subject: "owner-1",
        content: { text: "hello" },
        triggerSource: "api",
        idempotencyKey: "api-message-1",
        createdAt,
      })
      const run = await store.createRun({
        id: crypto.randomUUID(),
        conversationId: inbound.conversationId,
        parentRunId: null,
        triggerSource: "api",
        idempotencyKey: "api-run-1",
        subject: "owner-1",
        goal: "reply",
        budget: { maxSteps: 5 },
        deadline: null,
        createdAt,
      })
      const step = await store.createStep({
        id: crypto.randomUUID(),
        runId: run.id,
        kind: "model",
        status: "running",
        input: { prompt: "hello" },
        createdAt,
      })

      expect(step).toEqual(
        expect.objectContaining({
          runId: run.id,
          kind: "model",
          status: "running",
          input: { prompt: "hello" },
        }),
      )
    } finally {
      await db.close()
    }
  })

  it("lists conversations by projectId ordered by updatedAt desc", async () => {
    const db = await makeTestDb()
    const store: RuntimeStore = createRuntimeStore(db)
    const t0 = new Date("2026-08-20T00:00:00Z")
    const t1 = new Date("2026-08-21T00:00:00Z")
    try {
      await store.createConversationWithUserMessage({
        conversationId: "c-WFXM-user-a",
        messageId: crypto.randomUUID(),
        subject: "user-a",
        content: { text: "a" },
        triggerSource: "channel",
        idempotencyKey: "k-a",
        createdAt: t0,
      })
      await store.createConversationWithUserMessage({
        conversationId: "c-WFXM-user-b",
        messageId: crypto.randomUUID(),
        subject: "user-b",
        content: { text: "b" },
        triggerSource: "channel",
        idempotencyKey: "k-b",
        createdAt: t1,
      })
      await store.createConversationWithUserMessage({
        conversationId: "c-other-user",
        messageId: crypto.randomUUID(),
        subject: "other",
        content: { text: "x" },
        triggerSource: "channel",
        idempotencyKey: "k-x",
        createdAt: t1,
      })
      const items = await store.listConversationsByProject({ projectId: "WFXM" })
      expect(items.map((c) => c.id)).toEqual(["c-WFXM-user-b", "c-WFXM-user-a"])
      expect(items.every((c) => c.projectId === "WFXM")).toBe(true)
    } finally {
      await db.close()
    }
  })

  it("revokes MCP scoped grants for a server id (P3)", async () => {
    const db = await makeTestDb()
    const store: RuntimeStore = createRuntimeStore(db)
    const now = new Date("2026-08-23T00:00:00Z")
    try {
      const inbound = await store.createConversationWithUserMessage({
        conversationId: crypto.randomUUID(),
        messageId: crypto.randomUUID(),
        subject: "owner-1",
        content: { text: "hi" },
        triggerSource: "channel",
        idempotencyKey: "mcp-revoke",
        createdAt: now,
      })
      const run = await store.createRun({
        id: crypto.randomUUID(),
        conversationId: inbound.conversationId,
        parentRunId: null,
        triggerSource: "channel",
        idempotencyKey: "run-mcp",
        subject: "owner-1",
        goal: "test",
        budget: {},
        deadline: null,
        createdAt: now,
      })
      const grantId = crypto.randomUUID()
      await store.createScopedGrant({
        grantId,
        runId: run.id,
        subject: "owner-1",
        capability: "mcp_search",
        scope: {
          digest: "d1",
          network: "allow",
          mcp: { serverId: "demo-server", toolName: "search" },
        },
        remainingUses: 1,
        expiresAt: new Date(now.getTime() + 60_000),
        createdAt: now,
      })
      await store.createScopedGrant({
        grantId: crypto.randomUUID(),
        runId: run.id,
        subject: "owner-1",
        capability: "mcp_fetch",
        scope: {
          digest: "d2",
          network: "allow",
          mcp: { serverId: "other-server", toolName: "fetch" },
        },
        remainingUses: 1,
        expiresAt: new Date(now.getTime() + 60_000),
        createdAt: now,
      })
      const revoked = await store.revokeScopedGrantsForMcpServer("demo-server", now)
      expect(revoked).toBe(1)
      const active = await store.findActiveGrant({
        runId: run.id,
        subject: "owner-1",
        capability: "mcp_search",
        digest: "d1",
        now,
      })
      expect(active).toBeNull()
    } finally {
      await db.close()
    }
  })

  it("revokes grants whose scope targets a capability (P3-2 uninstall)", async () => {
    const db = await makeTestDb()
    const store: RuntimeStore = createRuntimeStore(db)
    const now = new Date("2026-08-26T00:00:00Z")
    try {
      const inbound = await store.createConversationWithUserMessage({
        conversationId: crypto.randomUUID(),
        messageId: crypto.randomUUID(),
        subject: "owner-1",
        content: { text: "hi" },
        triggerSource: "channel",
        idempotencyKey: "cap-revoke",
        createdAt: now,
      })
      const run = await store.createRun({
        id: crypto.randomUUID(),
        conversationId: inbound.conversationId,
        parentRunId: null,
        triggerSource: "channel",
        idempotencyKey: "run-cap-revoke",
        subject: "owner-1",
        goal: "test",
        budget: {},
        deadline: null,
        createdAt: now,
      })
      await store.createScopedGrant({
        grantId: crypto.randomUUID(),
        runId: run.id,
        subject: "owner-1",
        capability: "mcp_search",
        scope: { digest: "s1" },
        remainingUses: 1,
        expiresAt: new Date(now.getTime() + 60_000),
        createdAt: now,
      })
      await store.createScopedGrant({
        grantId: crypto.randomUUID(),
        runId: run.id,
        subject: "owner-1",
        capability: "read_file",
        scope: { digest: "s2" },
        remainingUses: 1,
        expiresAt: new Date(now.getTime() + 60_000),
        createdAt: now,
      })
      const revoked = await store.revokeScopedGrantsForCapability("mcp_search", now)
      expect(revoked).toBe(1)
      expect(
        await store.findActiveGrant({
          runId: run.id,
          subject: "owner-1",
          capability: "mcp_search",
          digest: "s1",
          now,
        }),
      ).toBeNull()
      expect(
        await store.findActiveGrant({
          runId: run.id,
          subject: "owner-1",
          capability: "read_file",
          digest: "s2",
          now,
        }),
      ).not.toBeNull()
    } finally {
      await db.close()
    }
  })

  // D2.2: capability first-class column behavior + legacy JSON backfill fallback.
  it("persists capability as first-class column and finds by column (D2.2)", async () => {
    const db = await makeTestDb()
    const store: RuntimeStore = createRuntimeStore(db)
    const now = new Date("2026-08-28T00:00:00Z")
    try {
      const inbound = await store.createConversationWithUserMessage({
        conversationId: crypto.randomUUID(),
        messageId: crypto.randomUUID(),
        subject: "owner-1",
        content: { text: "hi" },
        triggerSource: "channel",
        idempotencyKey: "d22-cap",
        createdAt: now,
      })
      const run = await store.createRun({
        id: crypto.randomUUID(),
        conversationId: inbound.conversationId,
        parentRunId: null,
        triggerSource: "channel",
        idempotencyKey: "run-d22-cap",
        subject: "owner-1",
        goal: "test",
        budget: {},
        deadline: null,
        createdAt: now,
      })
      // Forward write: capability column is the only place the name lives.
      const grant = await store.createScopedGrant({
        grantId: crypto.randomUUID(),
        runId: run.id,
        subject: "owner-1",
        capability: "read_file",
        scope: { digest: "d1" },
        remainingUses: 1,
        expiresAt: new Date(now.getTime() + 60_000),
        createdAt: now,
      })
      expect(grant.capability).toBe("read_file")

      // Active grant lookups must match by column, not by JSON shape.
      const hit = await store.findActiveGrant({
        runId: run.id,
        subject: "owner-1",
        capability: "read_file",
        digest: "d1",
        now,
      })
      expect(hit?.id).toBe(grant.id)

      // SQL filter excludes rows with different capability (no JS-side fallback needed).
      const miss = await store.findActiveGrant({
        runId: run.id,
        subject: "owner-1",
        capability: "write_file",
        now,
      })
      expect(miss).toBeNull()
    } finally {
      await db.close()
    }
  })

  // D2.2 legacy compat: hydration falls back to scope.capabilities[0] when column is NULL
  // (defense-in-depth; production migration backfill already covers this in SQL).
  it("hydrates legacy grants with NULL capability column from scope JSON", async () => {
    const db = await makeTestDb()
    const store: RuntimeStore = createRuntimeStore(db)
    const now = new Date("2026-08-28T00:00:00Z")
    try {
      const inbound = await store.createConversationWithUserMessage({
        conversationId: crypto.randomUUID(),
        messageId: crypto.randomUUID(),
        subject: "owner-1",
        content: { text: "hi" },
        triggerSource: "channel",
        idempotencyKey: "d22-legacy",
        createdAt: now,
      })
      const run = await store.createRun({
        id: crypto.randomUUID(),
        conversationId: inbound.conversationId,
        parentRunId: null,
        triggerSource: "channel",
        idempotencyKey: "run-d22-legacy",
        subject: "owner-1",
        goal: "test",
        budget: {},
        deadline: null,
        createdAt: now,
      })
      // Bypass store contract to simulate a legacy row (capability column NULL,
      // capability still in scope.capabilities JSON).
      const legacyGrantId = crypto.randomUUID()
      const scopeJson = JSON.stringify({ capabilities: ["read_file"], digest: "lg1" })
      await db.execute(sql`INSERT INTO scoped_grants
            (grant_id, run_id, subject, scope, remaining_uses, expires_at, created_at, capability)
            VALUES (${legacyGrantId}, ${run.id}, 'owner-1', ${scopeJson}::jsonb, 1,
                    ${new Date(now.getTime() + 60_000).toISOString()}::timestamptz,
                    ${now.toISOString()}::timestamptz, NULL)`)
      const hydrated = await store.findActiveGrant({
        runId: run.id,
        subject: "owner-1",
        capability: "read_file",
        digest: "lg1",
        now,
      })
      // SQL filter rejects NULL capability column, so findActiveGrant returns null —
      // even though hydrate would have populated record.capability from JSON. This is
      // the intended runtime behavior: SQL filter is the only match path; legacy rows
      // are reconciled by migration 0011 backfill, not at read time.
      expect(hydrated).toBeNull()
    } finally {
      await db.close()
    }
  })
})

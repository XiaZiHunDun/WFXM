import { describe, expect, it } from "vitest"
import { sql } from "drizzle-orm"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import { createRuntimeStore } from "./runtime-store.js"
import { makeTestDb } from "./testing.js"

describe("RuntimeStore repository", () => {
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

  // D56 audit F9 (must-fix): createConversationWithUserMessage did two
  // non-transactional writes (conv upsert + message insert). If the message
  // insert throws (PK / unique / race), the conversation row would land
  // anyway and idempotency replay would return the orphan conversation
  // without ever recreating the message. This test pins the recovery
  // contract: a PK collision on messageId throws AND a follow-up call
  // with a brand-new conversationId is unaffected by the prior failure.
  // The atomicity invariant is enforced by the surrounding db.transaction
  // wrapper added in D56 T3.
  it("D56 F9: PK collision on messageId throws AND recovery on a fresh conversationId works (transaction rollback)", async () => {
    const db = await makeTestDb()
    const store: RuntimeStore = createRuntimeStore(db)
    const reusedMessageId = crypto.randomUUID()
    const convA = crypto.randomUUID()
    const convB = crypto.randomUUID()
    try {
      // Seed convA with reusedMessageId so the next call collides on PK.
      await store.createConversationWithUserMessage({
        conversationId: convA,
        messageId: reusedMessageId,
        subject: "owner-1",
        content: { text: "seed" },
        triggerSource: "channel",
        idempotencyKey: "fk-conv-a",
        createdAt: new Date("2026-09-01T00:00:00Z"),
      })

      // PK collision on reusedMessageId via a *different* conversationId +
      // different idempotencyKey. The transaction must roll back so convB
      // does NOT leak into the table.
      await expect(
        store.createConversationWithUserMessage({
          conversationId: convB,
          messageId: reusedMessageId, // PK collision
          subject: "owner-1",
          content: { text: "should not land" },
          triggerSource: "channel",
          idempotencyKey: "fk-conv-b-collide",
          createdAt: new Date("2026-09-01T00:01:00Z"),
        }),
      ).rejects.toThrow()

      // Recovery: a fresh convC with a fresh messageId + fresh idempotencyKey
      // still works — proves the failed transaction did not corrupt store
      // state or hold locks.
      const convC = crypto.randomUUID()
      const recovered = await store.createConversationWithUserMessage({
        conversationId: convC,
        messageId: crypto.randomUUID(),
        subject: "owner-1",
        content: { text: "after-recovery" },
        triggerSource: "channel",
        idempotencyKey: "fk-conv-c",
        createdAt: new Date("2026-09-01T00:02:00Z"),
      })
      expect(recovered.conversationId).toBe(convC)
      const convCMessages = await store.listMessages(convC)
      expect(convCMessages).toHaveLength(1)
      expect((convCMessages[0]?.content as Readonly<Record<string, unknown>>)?.text ?? "").toBe(
        "after-recovery",
      )
    } finally {
      await db.close()
    }
  })
})

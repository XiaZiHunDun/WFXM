import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import { revokeScopedGrantsForMcpServer } from "./mcp-grant-lifecycle.js"

describe("mcp-grant-lifecycle", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>

  beforeEach(async () => {
    db = await makeTestDb()
  })

  afterEach(async () => {
    await db.close()
  })

  async function seedServerGrant(store: RuntimeStore, serverId: string) {
    const createdAt = new Date("2026-08-20T00:00:00Z")
    const inbound = await store.createConversationWithUserMessage({
      conversationId: crypto.randomUUID(),
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "hi" },
      triggerSource: "channel",
      idempotencyKey: crypto.randomUUID(),
      createdAt,
    })
    const run = await store.createRun({
      id: crypto.randomUUID(),
      conversationId: inbound.conversationId,
      parentRunId: null,
      triggerSource: "channel",
      idempotencyKey: crypto.randomUUID(),
      subject: "owner-1",
      goal: "mcp",
      budget: {},
      deadline: null,
      createdAt,
    })
    await store.createScopedGrant({
      grantId: crypto.randomUUID(),
      runId: run.id,
      subject: "owner-1",
      capability: `mcp:${serverId}:read`,
      scope: { mcp: { serverId, toolName: "read" } },
      remainingUses: 3,
      expiresAt: new Date("2099-01-01T00:00:00Z"),
      createdAt,
    })
  }

  it("revokeScopedGrantsForMcpServer normalizes the server id and revokes its grants", async () => {
    const store = createRuntimeStore(db.db)
    await seedServerGrant(store, "github")
    const revoked = await revokeScopedGrantsForMcpServer(store, "  GitHub  ")
    expect(revoked).toBe(1)
    const active = await store.countActiveScopedGrantsForMcpServer(
      "github",
      new Date("2026-08-21T00:00:00Z"),
    )
    expect(active).toBe(0)
  })

  it("revokeScopedGrantsForMcpServer leaves grants of other servers untouched", async () => {
    const store = createRuntimeStore(db.db)
    await seedServerGrant(store, "github")
    const revoked = await revokeScopedGrantsForMcpServer(store, "slack")
    expect(revoked).toBe(0)
    const active = await store.countActiveScopedGrantsForMcpServer(
      "github",
      new Date("2026-08-21T00:00:00Z"),
    )
    expect(active).toBe(1)
  })
})

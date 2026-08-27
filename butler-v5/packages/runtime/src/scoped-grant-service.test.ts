import { describe, expect, it } from "vitest"
import { makeTestDb } from "@butler/persistence/testing.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { issuePreconfiguredGrants } from "./scoped-grant-service.js"

describe("issuePreconfiguredGrants", () => {
  it("issues grants and skips duplicates unless refreshExisting", async () => {
    const db = await makeTestDb()
    const store = createRuntimeStore(db.db)
    const createdAt = new Date()
    const inbound = await store.createConversationWithUserMessage({
      conversationId: "c-grant-svc",
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "hi" },
      triggerSource: "channel",
      idempotencyKey: "grant-svc-msg",
      createdAt,
    })
    const run = await store.createRun({
      id: crypto.randomUUID(),
      conversationId: inbound.conversationId,
      parentRunId: null,
      triggerSource: "api",
      idempotencyKey: "grant-svc-run",
      subject: "owner-1",
      goal: "grant-svc",
      budget: { maxSteps: 1 },
      deadline: null,
      createdAt,
    })

    const first = await issuePreconfiguredGrants({
      store,
      runId: run.id,
      subject: "owner-1",
      capabilities: ["run_command", "write_file"],
      maxUses: 3,
      ttlMs: 60_000,
      createdAt,
    })
    expect(first).toHaveLength(2)

    const second = await issuePreconfiguredGrants({
      store,
      runId: run.id,
      subject: "owner-1",
      capabilities: ["run_command", "write_file"],
      maxUses: 3,
      ttlMs: 60_000,
      createdAt,
    })
    expect(second).toHaveLength(0)

    const refreshed = await issuePreconfiguredGrants({
      store,
      runId: run.id,
      subject: "owner-1",
      capabilities: ["run_command"],
      maxUses: 5,
      ttlMs: 60_000,
      refreshExisting: true,
      createdAt,
    })
    expect(refreshed).toHaveLength(1)
    expect(refreshed[0]?.remainingUses).toBe(5)

    await db.close()
  })

  it("child run cannot reuse parent run grants", async () => {
    const db = await makeTestDb()
    const store = createRuntimeStore(db.db)
    const createdAt = new Date()
    const inbound = await store.createConversationWithUserMessage({
      conversationId: "c-parent-child-grant",
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "hi" },
      triggerSource: "channel",
      idempotencyKey: "parent-child-msg",
      createdAt,
    })
    const parent = await store.createRun({
      id: crypto.randomUUID(),
      conversationId: inbound.conversationId,
      parentRunId: null,
      triggerSource: "channel",
      idempotencyKey: "parent-run",
      subject: "owner-1",
      goal: "parent",
      budget: { maxSteps: 1 },
      deadline: null,
      createdAt,
    })
    const child = await store.createRun({
      id: crypto.randomUUID(),
      conversationId: inbound.conversationId,
      parentRunId: parent.id,
      triggerSource: "parent_run",
      idempotencyKey: "child-run",
      subject: "owner-1",
      goal: "child",
      budget: { maxSteps: 1 },
      deadline: null,
      createdAt,
    })

    await issuePreconfiguredGrants({
      store,
      runId: parent.id,
      subject: "owner-1",
      capabilities: ["run_command"],
      maxUses: 2,
      ttlMs: 60_000,
      createdAt,
    })

    const onChild = await store.findActiveGrant({
      runId: child.id,
      subject: "owner-1",
      capability: "run_command",
      now: new Date(),
    })
    expect(onChild).toBeNull()

    await db.close()
  })
})

import { describe, expect, it } from "vitest"
import { makeTestDb } from "@butler/persistence/testing.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { delegationPregrantCapabilities, ensureDelegationToolGrants } from "./delegation-grants.js"

describe("ensureDelegationToolGrants", () => {
  it("issues multi-use grants for delegated run_command and write_file", async () => {
    const db = await makeTestDb()
    const store = createRuntimeStore(db.db)
    const createdAt = new Date()
    const inbound = await store.createConversationWithUserMessage({
      conversationId: "c-delegate-grant",
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "delegate" },
      triggerSource: "channel",
      idempotencyKey: "delegate-grant-msg",
      createdAt,
    })
    const run = await store.createRun({
      id: crypto.randomUUID(),
      conversationId: inbound.conversationId,
      parentRunId: null,
      triggerSource: "parent_run",
      idempotencyKey: "delegate-grant-run",
      subject: "owner-1",
      goal: "child",
      budget: { maxSteps: 3 },
      deadline: null,
      createdAt,
    })
    await ensureDelegationToolGrants({
      store,
      childRunId: run.id,
      ownerSubject: "owner-1",
      capabilities: ["general", "run_command", "write_file"],
      maxUses: 3,
      env: { BUTLER_V5_SANDBOX_NETWORK_MODE: "binary" } as NodeJS.ProcessEnv,
    })
    const cmd = await store.findActiveGrant({
      runId: run.id,
      subject: "owner-1",
      capability: "run_command",
      now: new Date(),
    })
    const write = await store.findActiveGrant({
      runId: run.id,
      subject: "owner-1",
      capability: "write_file",
      now: new Date(),
    })
    expect(cmd?.remainingUses).toBe(3)
    expect(write?.remainingUses).toBe(3)
    await db.close()
  })

  it("skips run_command pre-grant when sandbox network mode is allowlist", async () => {
    const db = await makeTestDb()
    const store = createRuntimeStore(db.db)
    const createdAt = new Date()
    const inbound = await store.createConversationWithUserMessage({
      conversationId: "c-delegate-allowlist",
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "delegate" },
      triggerSource: "channel",
      idempotencyKey: "delegate-allowlist-msg",
      createdAt,
    })
    const run = await store.createRun({
      id: crypto.randomUUID(),
      conversationId: inbound.conversationId,
      parentRunId: null,
      triggerSource: "parent_run",
      idempotencyKey: "delegate-allowlist-run",
      subject: "owner-1",
      goal: "child",
      budget: { maxSteps: 3 },
      deadline: null,
      createdAt,
    })
    const env = {
      BUTLER_V5_SANDBOX_NETWORK_MODE: "allowlist",
    } as NodeJS.ProcessEnv
    expect(
      delegationPregrantCapabilities({
        capabilities: ["run_command", "write_file"],
        env,
      }),
    ).toEqual(["write_file"])
    await ensureDelegationToolGrants({
      store,
      childRunId: run.id,
      ownerSubject: "owner-1",
      capabilities: ["general", "run_command", "write_file"],
      maxUses: 3,
      env,
    })
    const cmd = await store.findActiveGrant({
      runId: run.id,
      subject: "owner-1",
      capability: "run_command",
      now: new Date(),
    })
    const write = await store.findActiveGrant({
      runId: run.id,
      subject: "owner-1",
      capability: "write_file",
      now: new Date(),
    })
    expect(cmd).toBeNull()
    expect(write?.remainingUses).toBe(3)
    await db.close()
  })
})

import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import { createWaitingApprovalStep } from "@butler/runtime/approval-runtime.js"
import { EventBridge } from "@butler/runtime/bridge.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { makeWiring } from "./wiring.js"
import { tryWechatInlineApproval } from "./wechat-inline-approval.js"

describe("tryWechatInlineApproval", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>

  beforeEach(async () => {
    db = await makeTestDb()
    process.env["BUTLER_OWNER_WECHAT_ID"] = "owner-1"
  })

  afterEach(async () => {
    await db.close()
  })

  it("returns null for non-approval messages", async () => {
    const runtimeStore = createRuntimeStore(db.db)
    const wiring = makeWiring({
      bridge: new EventBridge({ db: db.db, workerId: "test" }),
      workerId: "test",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      backfillConversation: async () => undefined,
    })
    const out = await tryWechatInlineApproval({
      wiring,
      conversationId: "conv-inline",
      content: "今天天气怎么样",
      fromUserId: "owner-1",
    })
    expect(out).toBeNull()
  })

  it("approves the latest pending step when user replies 确认", async () => {
    const runtimeStore = createRuntimeStore(db.db)
    const wiring = makeWiring({
      bridge: new EventBridge({ db: db.db, workerId: "test" }),
      workerId: "test",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      backfillConversation: async () => undefined,
    })
    const createdAt = new Date("2026-08-20T00:00:00Z")
    const inbound = await runtimeStore.createConversationWithUserMessage({
      conversationId: "conv-inline-approve",
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "send" },
      triggerSource: "channel",
      idempotencyKey: "inline-msg",
      createdAt,
    })
    const run = await runtimeStore.createRun({
      id: crypto.randomUUID(),
      conversationId: inbound.conversationId,
      parentRunId: null,
      triggerSource: "channel",
      idempotencyKey: "inline-run",
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
      capability: "get_current_time",
      resource: inbound.conversationId,
      args: {},
      question: "Confirm?",
      expiresAtMs: Date.now() + 60_000,
      digest: "inline-digest",
      kind: "read",
      risk: "low",
    })

    const out = await tryWechatInlineApproval({
      wiring,
      conversationId: inbound.conversationId,
      content: "确认",
      fromUserId: "owner-1",
    })
    expect(out).not.toBeNull()
    expect(out?.reply).toBeTruthy()
    expect(out?.toolCalls).toBe(1)
    const updatedRun = await runtimeStore.getRun(run.id)
    expect(updatedRun?.status).toBe("succeeded")
  })
})

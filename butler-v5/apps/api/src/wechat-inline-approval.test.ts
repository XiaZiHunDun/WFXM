import { describe, expect, it, beforeEach, afterEach, vi } from "vitest"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import { createWaitingApprovalStep } from "@butler/runtime/approval-runtime.js"
import { EventBridge } from "@butler/persistence/event-bridge.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { makeWiring } from "./wiring.js"
import { tryWechatInlineApproval } from "./wechat-inline-approval.js"

describe("tryWechatInlineApproval", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>

  beforeEach(async () => {
    vi.stubEnv("ANTHROPIC_API_KEY", "")
    vi.stubEnv("DEEPSEEK_API_KEY", "")
    vi.stubEnv("MINIMAX_API_KEY", "")
    vi.stubEnv("DASHSCOPE_API_KEY", "")
    db = await makeTestDb()
    process.env["BUTLER_OWNER_WECHAT_ID"] = "owner-1"
  })

  afterEach(async () => {
    vi.unstubAllEnvs()
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
    const active = await runtimeStore.findActiveMainRun(inbound.conversationId)
    expect(active).toBeNull()
  })

  // D67 T1b — consume-path bridge for fatigue_checklist steps. The new
  // T1a step shape (`{ reason: "fatigue_checklist", toolName, items }`)
  // does NOT match `parsePendingCapabilityInput`. The inline-approval
  // handler must detect this shape BEFORE the PendingCapabilityInput
  // parse, ack the step as succeeded, and return an owner-jargon reply
  // (D48: contains "已升级" + "确认").
  it("acks fatigue_checklist step via T1b bridge without trying parsePendingCapabilityInput", async () => {
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
      conversationId: "conv-fatigue-bridge",
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "send the file" },
      triggerSource: "channel",
      idempotencyKey: "fatigue-bridge-msg",
      createdAt,
    })
    const run = await runtimeStore.createRun({
      id: crypto.randomUUID(),
      conversationId: inbound.conversationId,
      parentRunId: null,
      triggerSource: "channel",
      idempotencyKey: "fatigue-bridge-run",
      subject: "owner-1",
      goal: "send_wechat_file",
      budget: { maxSteps: 5 },
      deadline: null,
      createdAt,
    })
    await runtimeStore.transitionRunStatus(run.id, run.version, "waiting_approval", createdAt)
    // T1a shape: NOT a PendingCapabilityInput; reason discriminator.
    const step = await runtimeStore.createStep({
      id: crypto.randomUUID(),
      runId: run.id,
      kind: "approval",
      status: "waiting",
      input: {
        reason: "fatigue_checklist",
        toolName: "send_wechat_file",
        items: ["不可撤销：发送到你的微信", "目标: README.md"],
      },
      createdAt,
    })
    const out = await tryWechatInlineApproval({
      wiring,
      conversationId: inbound.conversationId,
      content: "确认",
      fromUserId: "owner-1",
    })
    expect(out).not.toBeNull()
    expect(out?.reply).toContain("已升级")
    expect(out?.reply).toContain("确认")
    expect(out?.reply).toContain("send_wechat_file")
    expect(out?.finalDecision).toBe("Respond")
    // Step should now be marked succeeded.
    const updated = await runtimeStore.getStep(step.id)
    expect(updated?.status).toBe("succeeded")
    expect(updated?.output).toMatchObject({
      approvedBy: "owner-1",
      reason: "fatigue_checklist_ack",
      toolName: "send_wechat_file",
    })
  })

  it("acks fatigue_checklist deny via T1b bridge (failed step + deny reply)", async () => {
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
      conversationId: "conv-fatigue-bridge-deny",
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "send the file" },
      triggerSource: "channel",
      idempotencyKey: "fatigue-bridge-deny-msg",
      createdAt,
    })
    const run = await runtimeStore.createRun({
      id: crypto.randomUUID(),
      conversationId: inbound.conversationId,
      parentRunId: null,
      triggerSource: "channel",
      idempotencyKey: "fatigue-bridge-deny-run",
      subject: "owner-1",
      goal: "send_wechat_file",
      budget: { maxSteps: 5 },
      deadline: null,
      createdAt,
    })
    await runtimeStore.transitionRunStatus(run.id, run.version, "waiting_approval", createdAt)
    const step = await runtimeStore.createStep({
      id: crypto.randomUUID(),
      runId: run.id,
      kind: "approval",
      status: "waiting",
      input: {
        reason: "fatigue_checklist",
        toolName: "send_wechat_file",
        items: ["不可撤销：发送到你的微信"],
      },
      createdAt,
    })
    const out = await tryWechatInlineApproval({
      wiring,
      conversationId: inbound.conversationId,
      content: "拒绝",
      fromUserId: "owner-1",
    })
    expect(out).not.toBeNull()
    expect(out?.reply).toContain("已升级拒绝")
    expect(out?.finalDecision).toBe("Respond")
    const updated = await runtimeStore.getStep(step.id)
    expect(updated?.status).toBe("failed")
    expect(updated?.output).toMatchObject({
      deniedBy: "owner-1",
      reason: "fatigue_checklist_denied",
    })
  })
})

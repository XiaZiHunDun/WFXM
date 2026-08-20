import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import {
  approveWaitingStep,
  createWaitingApprovalStep,
  denyWaitingStep,
} from "./approval-runtime.js"

describe("approval-runtime", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>

  beforeEach(async () => {
    db = await makeTestDb()
  })

  afterEach(async () => {
    await db.close()
  })

  async function seedRunningRun() {
    const store = createRuntimeStore(db.db)
    const createdAt = new Date("2026-08-20T00:00:00Z")
    const inbound = await store.createConversationWithUserMessage({
      conversationId: "conv-approval",
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "send file" },
      triggerSource: "channel",
      idempotencyKey: "approval-msg-1",
      createdAt,
    })
    const run = await store.createRun({
      id: crypto.randomUUID(),
      conversationId: inbound.conversationId,
      parentRunId: null,
      triggerSource: "channel",
      idempotencyKey: "approval-run-1",
      subject: "owner-1",
      goal: "reply",
      budget: { maxSteps: 5 },
      deadline: null,
      createdAt,
    })
    const running = await store.transitionRunStatus(run.id, run.version, "running", createdAt)
    return { store, run: running, conversationId: inbound.conversationId }
  }

  it("creates a waiting approval step and transitions the run", async () => {
    const { store, run, conversationId } = await seedRunningRun()
    const { stepId } = await createWaitingApprovalStep(store, {
      runId: run.id,
      conversationId,
      subject: "owner-1",
      capability: "send_wechat_file",
      resource: "photo.jpg",
      args: { path: "photo.jpg" },
      question: "Confirm send_wechat_file on photo.jpg?",
      expiresAtMs: Date.now() + 60_000,
      digest: "send_wechat_file:photo.jpg:{}",
      kind: "outbound",
      risk: "medium",
    })
    const step = await store.getStep(stepId)
    expect(step?.kind).toBe("approval")
    expect(step?.status).toBe("waiting")
    const updatedRun = await store.getRun(run.id)
    expect(updatedRun?.status).toBe("waiting_approval")
    const waiting = await store.listWaitingApprovalSteps()
    expect(waiting.some((row) => row.id === stepId)).toBe(true)
  })

  it("approveWaitingStep issues a scoped grant and resumes the run", async () => {
    const { store, run, conversationId } = await seedRunningRun()
    const { stepId } = await createWaitingApprovalStep(store, {
      runId: run.id,
      conversationId,
      subject: "owner-1",
      capability: "send_wechat_file",
      resource: "photo.jpg",
      args: { path: "photo.jpg" },
      question: "Confirm?",
      expiresAtMs: Date.now() + 60_000,
      digest: "d1",
      kind: "outbound",
      risk: "medium",
    })
    const decision = await approveWaitingStep(store, stepId, "owner-1")
    expect(decision.grant.scope.capabilities).toEqual(["send_wechat_file"])
    expect(decision.grant.remainingUses).toBe(1)
    const updatedRun = await store.getRun(run.id)
    expect(updatedRun?.status).toBe("running")
    const step = await store.getStep(stepId)
    expect(step?.status).toBe("succeeded")
    await store.updateScopedGrantRemainingUses(decision.grant.id, 0)
    const exhausted = await store.findActiveGrant({
      runId: run.id,
      subject: "owner-1",
      capability: "send_wechat_file",
      now: new Date(),
    })
    expect(exhausted).toBeNull()
  })

  it("denyWaitingStep marks the step and run failed", async () => {
    const { store, run, conversationId } = await seedRunningRun()
    const { stepId } = await createWaitingApprovalStep(store, {
      runId: run.id,
      conversationId,
      subject: "owner-1",
      capability: "send_wechat_file",
      resource: "photo.jpg",
      args: { path: "photo.jpg" },
      question: "Confirm?",
      expiresAtMs: Date.now() + 60_000,
      digest: "d1",
      kind: "outbound",
      risk: "medium",
    })
    await denyWaitingStep(store, stepId, "owner-1")
    const step = await store.getStep(stepId)
    expect(step?.status).toBe("failed")
    const updatedRun = await store.getRun(run.id)
    expect(updatedRun?.status).toBe("failed")
  })
})

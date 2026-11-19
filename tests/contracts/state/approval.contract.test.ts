// 锚定契约：待审批进入 waiting_approval、确认/拒绝后的 Run/Step 终态、重复确认与拒绝幂等、过期审批不发放授权。
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import type { RuntimeStore, StoredRun } from "../../../packages/domain/src/runtime/index.js"
import { createRuntimeStore } from "../../../packages/persistence/src/runtime-store.js"
import { makeTestDb } from "../../../packages/persistence/src/testing.js"
import { scopedGrants } from "../../../packages/persistence/src/schema.js"
import {
  approveWaitingStep,
  createWaitingApprovalStep,
  denyWaitingStep,
  type PendingApprovalRequest,
} from "../../../packages/runtime/src/approval-runtime.js"
import { cancelRun } from "../../../packages/runtime/src/run-lifecycle.js"

const CREATED_AT = new Date("2026-10-01T00:00:00.000Z")

describe("approval lifecycle contract", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let store: RuntimeStore

  beforeEach(async () => {
    db = await makeTestDb()
    store = createRuntimeStore(db)
  })

  afterEach(async () => {
    await db.close()
  })

  async function seedRunningRun(): Promise<{
    readonly run: StoredRun
    readonly conversationId: string
  }> {
    const conversationId = crypto.randomUUID()
    await store.createConversationWithUserMessage({
      conversationId,
      messageId: crypto.randomUUID(),
      subject: "owner-contract",
      content: { text: "please send" },
      triggerSource: "channel",
      idempotencyKey: crypto.randomUUID(),
      createdAt: CREATED_AT,
    })
    const created = await store.createRun({
      id: crypto.randomUUID(),
      conversationId,
      parentRunId: null,
      triggerSource: "channel",
      idempotencyKey: crypto.randomUUID(),
      subject: "owner-contract",
      goal: "reply",
      budget: { maxSteps: 5 },
      deadline: null,
      createdAt: CREATED_AT,
    })
    const run = await store.transitionRunStatus(
      created.id,
      created.version,
      "running",
      new Date(CREATED_AT.getTime() + 1000),
    )
    return { run, conversationId }
  }

  function request(
    run: StoredRun,
    conversationId: string,
    overrides: Partial<PendingApprovalRequest> = {},
  ): PendingApprovalRequest {
    return {
      runId: run.id,
      conversationId,
      subject: "owner-contract",
      capability: "send_wechat_file",
      resource: "photo.jpg",
      args: { path: "photo.jpg" },
      question: "Send photo.jpg?",
      expiresAtMs: Date.now() + 60_000,
      digest: "digest-contract",
      kind: "outbound",
      risk: "medium",
      ...overrides,
    }
  }

  async function grantsForStep(stepId: string) {
    const all = await db.db.select().from(scopedGrants)
    return all.filter((grant) => grant.approvalId === stepId)
  }

  it("enters waiting_approval and exposes the pending step for the conversation", async () => {
    const { run, conversationId } = await seedRunningRun()
    const { stepId } = await createWaitingApprovalStep(store, request(run, conversationId))

    expect((await store.getRun(run.id))?.status).toBe("waiting_approval")
    const step = await store.getStep(stepId)
    expect(step?.kind).toBe("approval")
    expect(step?.status).toBe("waiting")

    const pending = await store.listWaitingApprovalStepsForConversation(conversationId)
    expect(pending.map((row) => row.id)).toContain(stepId)
    expect(await grantsForStep(stepId)).toHaveLength(0)
  })

  it("approves once, resumes the run, and acknowledges a repeated confirmation idempotently", async () => {
    const { run, conversationId } = await seedRunningRun()
    const { stepId } = await createWaitingApprovalStep(store, request(run, conversationId))

    const first = await approveWaitingStep(store, stepId, "owner-contract")
    expect(first._tag).toBe("approved")
    expect((await store.getStep(stepId))?.status).toBe("succeeded")
    const resumed = await store.getRun(run.id)
    expect(resumed?.status).toBe("running")
    expect(await grantsForStep(stepId)).toHaveLength(1)

    const replay = await approveWaitingStep(store, stepId, "owner-contract")
    expect(replay._tag).toBe("alreadyProcessed")
    expect(await grantsForStep(stepId)).toHaveLength(1)
    expect((await store.getStep(stepId))?.status).toBe("succeeded")
    // 重复确认不产生新的 Run 版本推进。
    expect((await store.getRun(run.id))?.version).toBe(resumed?.version)
  })

  it("denies once, marks run failed, and treats repeated deny or deny-after-approve as no-ops", async () => {
    const first = await seedRunningRun()
    const firstStep = await createWaitingApprovalStep(
      store,
      request(first.run, first.conversationId),
    )
    const denied = await denyWaitingStep(store, firstStep.stepId, "owner-contract")
    expect(denied.alreadyProcessed).toBe(false)
    expect((await store.getStep(firstStep.stepId))?.status).toBe("failed")
    expect((await store.getRun(first.run.id))?.status).toBe("failed")

    const repeat = await denyWaitingStep(store, firstStep.stepId, "owner-contract")
    expect(repeat.alreadyProcessed).toBe(true)
    expect((await store.getRun(first.run.id))?.status).toBe("failed")

    const second = await seedRunningRun()
    const secondStep = await createWaitingApprovalStep(
      store,
      request(second.run, second.conversationId, { digest: "digest-approve-then-deny" }),
    )
    const approved = await approveWaitingStep(store, secondStep.stepId, "owner-contract")
    expect(approved._tag).toBe("approved")
    const lateDeny = await denyWaitingStep(store, secondStep.stepId, "owner-contract")
    expect(lateDeny.alreadyProcessed).toBe(true)
    expect((await store.getStep(secondStep.stepId))?.status).toBe("succeeded")
    expect((await store.getRun(second.run.id))?.status).toBe("running")
  })

  it("never issues a grant for an expired approval and stays safe on retry", async () => {
    const { run, conversationId } = await seedRunningRun()
    const { stepId } = await createWaitingApprovalStep(
      store,
      request(run, conversationId, { expiresAtMs: Date.now() - 1, digest: "digest-expired" }),
    )

    const outcome = await approveWaitingStep(store, stepId, "owner-contract")
    expect(outcome._tag).toBe("alreadyProcessed")
    if (outcome._tag === "alreadyProcessed") expect(outcome.reason).toBe("expired")
    expect(await grantsForStep(stepId)).toHaveLength(0)
    expect((await store.getStep(stepId))?.status).toBe("failed")
    expect((await store.getRun(run.id))?.status).toBe("failed")

    const retry = await approveWaitingStep(store, stepId, "owner-contract")
    expect(retry._tag).toBe("alreadyProcessed")
    expect(await grantsForStep(stepId)).toHaveLength(0)
  })

  it("denies without resurrecting a run that was already cancelled", async () => {
    const { run, conversationId } = await seedRunningRun()
    const { stepId } = await createWaitingApprovalStep(store, request(run, conversationId))
    await cancelRun(store, run.id, { subject: "owner-contract", reason: "owner_cancel" })
    expect((await store.getRun(run.id))?.status).toBe("cancelled")

    const outcome = await denyWaitingStep(store, stepId, "owner-contract")
    expect(outcome.alreadyProcessed).toBe(false)
    expect((await store.getStep(stepId))?.status).toBe("failed")
    expect((await store.getRun(run.id))?.status).toBe("cancelled")
    expect(await grantsForStep(stepId)).toHaveLength(0)
  })

  it("rejects an unknown approval step without side effects", async () => {
    await expect(approveWaitingStep(store, crypto.randomUUID(), "owner-contract")).rejects.toThrow(
      /approval step not found/,
    )
    const all = await db.db.select().from(scopedGrants)
    expect(all).toHaveLength(0)
  })
})

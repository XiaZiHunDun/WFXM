import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import { auditEvents, scopedGrants } from "@butler/persistence/schema.js"
import { eq } from "drizzle-orm"
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
    expect(decision._tag).toBe("approved")
    if (decision._tag !== "approved") throw new Error("expected approved")
    expect(decision.grant.capability).toBe("send_wechat_file")
    expect(decision.grant.scope.paths).toEqual(["photo.jpg"])
    expect(decision.grant.scope.digest).toBe("d1")
    expect(decision.grant.scope.network).toBe("allow")
    expect(decision.grant.scope.networkHosts?.length).toBeGreaterThan(0)
    expect(decision.grant.remainingUses).toBe(1)
    expect(decision.grant.delegable).toBe(false)
    expect(decision.grant.approvalId).toBe(stepId)
    expect(decision.grant.sandboxProfile).toBeNull()
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

  it("approveWaitingStep binds sandboxProfile deny ceiling for run_command", async () => {
    const { store, run, conversationId } = await seedRunningRun()
    const { stepId } = await createWaitingApprovalStep(store, {
      runId: run.id,
      conversationId,
      subject: "owner-1",
      capability: "run_command",
      resource: "ls",
      args: { argv: ["ls"] },
      question: "Confirm run_command?",
      expiresAtMs: Date.now() + 60_000,
      digest: "run_command:ls",
      kind: "command",
      risk: "high",
    })
    const decision = await approveWaitingStep(store, stepId, "owner-1")
    if (decision._tag !== "approved") throw new Error("expected approved")
    expect(decision.grant.sandboxProfile).toBe("workspace-write-network-deny")
  })

  it("approveWaitingStep can elevate sandboxProfile to network-allow", async () => {
    const { store, run, conversationId } = await seedRunningRun()
    const { stepId } = await createWaitingApprovalStep(store, {
      runId: run.id,
      conversationId,
      subject: "owner-1",
      capability: "run_command",
      resource: "ls",
      args: { argv: ["ls"] },
      question: "Confirm run_command?",
      expiresAtMs: Date.now() + 60_000,
      digest: "run_command:ls:elevate",
      kind: "command",
      risk: "high",
    })
    const decision = await approveWaitingStep(store, stepId, "owner-1", {
      elevateNetwork: true,
    })
    if (decision._tag !== "approved") throw new Error("expected approved")
    expect(decision.grant.sandboxProfile).toBe("workspace-write-network-allow")
  })

  it("approveWaitingStep can stamp networkAllowlist on run_command", async () => {
    const { store, run, conversationId } = await seedRunningRun()
    const { stepId } = await createWaitingApprovalStep(store, {
      runId: run.id,
      conversationId,
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
    const decision = await approveWaitingStep(store, stepId, "owner-1", {
      networkAllowlist: ["registry.npmjs.org:443", "pypi.org"],
    })
    if (decision._tag !== "approved") throw new Error("expected approved")
    expect(decision.grant.sandboxProfile).toBe("workspace-write-network-allowlist")
    expect(decision.grant.networkAllowlist).toEqual(["registry.npmjs.org:443", "pypi.org:443"])
    expect(decision.grant.scope.network).toBe("allow")
    expect(decision.grant.scope.networkHosts).toContain("registry.npmjs.org")
  })

  it("rejects mutually exclusive elevateNetwork and networkAllowlist", async () => {
    const { store, run, conversationId } = await seedRunningRun()
    const { stepId } = await createWaitingApprovalStep(store, {
      runId: run.id,
      conversationId,
      subject: "owner-1",
      capability: "run_command",
      resource: "ls",
      args: { argv: ["ls"] },
      question: "Confirm?",
      expiresAtMs: Date.now() + 60_000,
      digest: "run_command:ls:conflict",
      kind: "command",
      risk: "high",
    })
    await expect(
      approveWaitingStep(store, stepId, "owner-1", {
        elevateNetwork: true,
        networkAllowlist: ["registry.npmjs.org:443"],
      }),
    ).rejects.toThrow(/mutually exclusive/)
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

  it("P1 idempotency: repeated approve does not double-issue a grant", async () => {
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
      digest: "idem-approve",
      kind: "outbound",
      risk: "medium",
    })
    const first = await approveWaitingStep(store, stepId, "owner-1")
    expect(first._tag).toBe("approved")
    if (first._tag !== "approved") throw new Error("expected approved")
    const second = await approveWaitingStep(store, stepId, "owner-1")
    expect(second._tag).toBe("alreadyProcessed")

    // Only one grant was issued for this approval step.
    const grants = await db.db
      .select()
      .from(scopedGrants)
      .where(eq(scopedGrants.approvalId, stepId))
    expect(grants).toHaveLength(1)
    // The run is not re-resumed to a phantom running state duplicate.
    const step = await store.getStep(stepId)
    expect(step?.status).toBe("succeeded")
  })

  it("P1 idempotency: deny after approve is a no-op (already processed)", async () => {
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
      digest: "idem-deny-after-approve",
      kind: "outbound",
      risk: "medium",
    })
    const approved = await approveWaitingStep(store, stepId, "owner-1")
    expect(approved._tag).toBe("approved")
    if (approved._tag !== "approved") throw new Error("expected approved")
    const reject = await denyWaitingStep(store, stepId, "owner-1")
    expect(reject.alreadyProcessed).toBe(true)
    // Deny does not overwrite the succeeded step nor add a second audit.
    const step = await store.getStep(stepId)
    expect(step?.status).toBe("succeeded")
  })

  it("P1 idempotency: repeat deny does not double-audit", async () => {
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
      digest: "idem-deny",
      kind: "outbound",
      risk: "medium",
    })
    const firstDeny = await denyWaitingStep(store, stepId, "owner-1")
    expect(firstDeny.alreadyProcessed).toBe(false)
    const secondDeny = await denyWaitingStep(store, stepId, "owner-1")
    expect(secondDeny.alreadyProcessed).toBe(true)
    const audits = await db.db.select().from(auditEvents)
    expect(audits.filter((a) => a.action === "approval.denied")).toHaveLength(1)
  })

  it("P1 idempotency: approve after expiry issues no grant (ack alreadyProcessed)", async () => {
    const { store, run, conversationId } = await seedRunningRun()
    const { stepId } = await createWaitingApprovalStep(store, {
      runId: run.id,
      conversationId,
      subject: "owner-1",
      capability: "send_wechat_file",
      resource: "photo.jpg",
      args: { path: "photo.jpg" },
      question: "Confirm?",
      expiresAtMs: Date.now() - 1,
      digest: "idem-expired",
      kind: "outbound",
      risk: "medium",
    })
    const outcome = await approveWaitingStep(store, stepId, "owner-1")
    expect(outcome._tag).toBe("alreadyProcessed")
    expect(outcome.reason).toBe("expired")
    const grants = await db.db
      .select()
      .from(scopedGrants)
      .where(eq(scopedGrants.approvalId, stepId))
    expect(grants).toHaveLength(0)
    const step = await store.getStep(stepId)
    expect(step?.status).toBe("failed")
  })
})

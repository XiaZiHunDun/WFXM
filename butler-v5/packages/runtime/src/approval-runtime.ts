import type { ActionKind, RiskLevel, ScopedGrantRecord } from "@butler/domain/governance/types.js"
import type { RuntimeStore, StoredStep } from "@butler/domain/runtime.js"

export interface PendingCapabilityInput {
  readonly _tag: "PendingCapability"
  readonly capability: string
  readonly args: Readonly<Record<string, unknown>>
  readonly conversationId: string
  readonly subject: string
  readonly resource: string
  readonly question: string
  readonly expiresAtMs: number
  readonly digest: string
  readonly kind: ActionKind
  readonly risk: RiskLevel
  readonly wechatUserId?: string
  readonly wechatContextToken?: string
}

export interface PendingApprovalRequest {
  readonly runId: string
  readonly conversationId: string
  readonly subject: string
  readonly capability: string
  readonly resource: string
  readonly args: Readonly<Record<string, unknown>>
  readonly question: string
  readonly expiresAtMs: number
  readonly digest: string
  readonly kind: ActionKind
  readonly risk: RiskLevel
  readonly wechatUserId?: string
  readonly wechatContextToken?: string
}

export function parsePendingCapabilityInput(
  input: Readonly<Record<string, unknown>>,
): PendingCapabilityInput | null {
  if (input["_tag"] !== "PendingCapability") return null
  const capability = input["capability"]
  const conversationId = input["conversationId"]
  const subject = input["subject"]
  const question = input["question"]
  if (
    typeof capability !== "string" ||
    typeof conversationId !== "string" ||
    typeof subject !== "string" ||
    typeof question !== "string"
  ) {
    return null
  }
  return input as unknown as PendingCapabilityInput
}

export async function createWaitingApprovalStep(
  store: RuntimeStore,
  request: PendingApprovalRequest,
): Promise<{ readonly stepId: string }> {
  const run = await store.getRun(request.runId)
  if (!run) {
    throw new Error(`run not found: ${request.runId}`)
  }
  await store.transitionRunStatus(run.id, run.version, "waiting_approval", new Date())
  const stepId = crypto.randomUUID()
  const now = new Date()
  const pending: PendingCapabilityInput = {
    _tag: "PendingCapability",
    capability: request.capability,
    args: request.args,
    conversationId: request.conversationId,
    subject: request.subject,
    resource: request.resource,
    question: request.question,
    expiresAtMs: request.expiresAtMs,
    digest: request.digest,
    kind: request.kind,
    risk: request.risk,
    ...(request.wechatUserId ? { wechatUserId: request.wechatUserId } : {}),
    ...(request.wechatContextToken ? { wechatContextToken: request.wechatContextToken } : {}),
  }
  await store.createStep({
    id: stepId,
    runId: request.runId,
    kind: "approval",
    status: "waiting",
    input: pending as unknown as Readonly<Record<string, unknown>>,
    createdAt: now,
  })
  await store.appendAuditEvent({
    auditId: crypto.randomUUID(),
    runId: request.runId,
    conversationId: request.conversationId,
    action: "approval.requested",
    subject: request.subject,
    detail: {
      stepId,
      capability: request.capability,
      digest: request.digest,
      question: request.question,
    },
    createdAt: now,
  })
  return { stepId }
}

export interface ApprovalDecision {
  readonly step: StoredStep
  readonly grant: ScopedGrantRecord
  readonly runId: string
}

export async function approveWaitingStep(
  store: RuntimeStore,
  stepId: string,
  ownerSubject: string,
): Promise<ApprovalDecision> {
  const step = await store.getStep(stepId)
  if (!step || step.kind !== "approval" || step.status !== "waiting") {
    throw new Error(`approval step not waiting: ${stepId}`)
  }
  const pending = parsePendingCapabilityInput(step.input)
  if (!pending) {
    throw new Error(`invalid pending capability on step ${stepId}`)
  }
  if (Date.now() > pending.expiresAtMs) {
    await denyWaitingStep(store, stepId, ownerSubject, "expired")
    throw new Error(`approval step expired: ${stepId}`)
  }
  const run = await store.getRun(step.runId)
  if (!run) {
    throw new Error(`run not found for step ${stepId}`)
  }
  const now = new Date()
  const grant = await store.createScopedGrant({
    grantId: crypto.randomUUID(),
    runId: step.runId,
    subject: pending.subject,
    scope: { capabilities: [pending.capability] },
    remainingUses: 1,
    expiresAt: new Date(pending.expiresAtMs),
    createdAt: now,
  })
  await store.updateStep({
    stepId,
    status: "succeeded",
    output: { approvedBy: ownerSubject, grantId: grant.id },
    updatedAt: now,
  })
  await store.transitionRunStatus(run.id, run.version, "running", now)
  await store.appendAuditEvent({
    auditId: crypto.randomUUID(),
    runId: step.runId,
    conversationId: pending.conversationId,
    action: "approval.granted",
    subject: ownerSubject,
    detail: { stepId, capability: pending.capability, grantId: grant.id },
    createdAt: now,
  })
  return { step, grant, runId: step.runId }
}

export async function denyWaitingStep(
  store: RuntimeStore,
  stepId: string,
  ownerSubject: string,
  reason = "denied",
): Promise<void> {
  const step = await store.getStep(stepId)
  if (!step) {
    throw new Error(`step not found: ${stepId}`)
  }
  const pending = parsePendingCapabilityInput(step.input)
  const now = new Date()
  await store.updateStep({
    stepId,
    status: "failed",
    output: { deniedBy: ownerSubject, reason },
    updatedAt: now,
  })
  const run = await store.getRun(step.runId)
  if (run && run.status === "waiting_approval") {
    await store.transitionRunStatus(run.id, run.version, "failed", now)
  }
  await store.appendAuditEvent({
    auditId: crypto.randomUUID(),
    runId: step.runId,
    conversationId: pending?.conversationId ?? null,
    action: "approval.denied",
    subject: ownerSubject,
    detail: { stepId, reason },
    createdAt: now,
  })
}

import type { RunTrigger } from "@butler/domain/runtime.js"
import {
  parsePendingCapabilityInput,
  type ApprovalDecision,
} from "@butler/runtime/approval-runtime.js"
import type { ScopedGrantRecord } from "@butler/domain/governance/types.js"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import { RunPauseForApproval } from "@butler/runtime/run-engine.js"
import type { ToolExecutionOutcome } from "@butler/runtime/capability-boundary.js"
import type { RunResult } from "@butler/runtime/tool-runtime.js"
import { findTool, makeWeibutlerTools } from "./tools.js"
import { makeToolExecutor, resolveOwnerSubject, toolTimeoutMs } from "./tool-boundary.js"
import type { Wiring } from "./wiring.js"

export { approveWaitingStep, denyWaitingStep } from "@butler/runtime/approval-runtime.js"

export async function markGrantConsumed(
  store: RuntimeStore,
  grant: ScopedGrantRecord,
): Promise<void> {
  if (grant.remainingUses === null) return
  await store.updateScopedGrantRemainingUses(grant.id, Math.max(0, grant.remainingUses - 1))
}

export function isPendingApprovalOutcome(
  outcome: ToolExecutionOutcome,
): outcome is Extract<ToolExecutionOutcome, { pendingApproval: unknown }> {
  return (
    outcome.ok === false &&
    "pendingApproval" in outcome &&
    outcome.pendingApproval !== undefined
  )
}

export function toRunResult(outcome: ToolExecutionOutcome): RunResult {
  if (outcome.ok) return outcome
  return { ok: false, reason: outcome.reason }
}

export async function resumeApprovedCapability(
  wiring: Wiring,
  decision: ApprovalDecision,
  options: {
    readonly env?: NodeJS.ProcessEnv
    readonly trigger?: RunTrigger
  } = {},
): Promise<RunResult> {
  const env = options.env ?? process.env
  const pending = parsePendingCapabilityInput(decision.step.input)
  if (!pending) {
    return { ok: false, reason: "invalid pending capability step" }
  }
  const tools = makeWeibutlerTools({
    bridge: wiring.eventBridge,
    conversationId: pending.conversationId,
    actor: { kind: "agent", id: "approval-resume" },
    ...(pending.wechatUserId ? { wechatUserId: pending.wechatUserId } : {}),
    ...(pending.wechatContextToken ? { wechatContextToken: pending.wechatContextToken } : {}),
    env,
  })
  const def = findTool(tools, pending.capability)
  if (!def) {
    return { ok: false, reason: `unknown capability: ${pending.capability}` }
  }
  const executor = makeToolExecutor({
    tools,
    store: wiring.runtimeStore,
    runId: decision.runId,
    ownerSubject: resolveOwnerSubject(env, pending.subject),
    subject: pending.subject,
    conversationId: pending.conversationId,
    timeoutMsFor: toolTimeoutMs,
    grant: decision.grant,
  })
  const outcome = await executor.execute(def, pending.args)
  if (isPendingApprovalOutcome(outcome)) {
    return { ok: false, reason: outcome.reason }
  }
  const result = toRunResult(outcome)
  const run = await wiring.runtimeStore.getRun(decision.runId)
  if (run) {
    const finalStatus = result.ok ? "succeeded" : "failed"
    await wiring.runtimeStore.transitionRunStatus(run.id, run.version, finalStatus, new Date())
  }
  if (options.trigger) {
    await wiring.runtimeStore.appendAuditEvent({
      auditId: crypto.randomUUID(),
      runId: decision.runId,
      conversationId: pending.conversationId,
      action: "approval.resume",
      subject: options.trigger.subject,
      detail: {
        stepId: decision.step.id,
        triggerSource: options.trigger.source,
        trustLevel: options.trigger.trustLevel,
        idempotencyKey: options.trigger.idempotencyKey,
        triggerPayload: options.trigger.payload,
      },
      createdAt: new Date(),
    })
  }
  if (result.ok) {
    await markGrantConsumed(wiring.runtimeStore, decision.grant)
    await wiring.runtimeStore.appendAuditEvent({
      auditId: crypto.randomUUID(),
      runId: decision.runId,
      conversationId: pending.conversationId,
      action: "approval.executed",
      subject: pending.subject,
      detail: {
        stepId: decision.step.id,
        capability: pending.capability,
        output: String(result.output),
      },
      createdAt: new Date(),
    })
  }
  return result
}

export function throwIfPendingApproval(
  outcome: ToolExecutionOutcome,
  pausePayload: unknown,
): RunResult {
  if (isPendingApprovalOutcome(outcome)) {
    throw new RunPauseForApproval(pausePayload)
  }
  return toRunResult(outcome)
}

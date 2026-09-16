import {
  approveWaitingStep,
  denyWaitingStep,
  parsePendingCapabilityInput,
} from "@butler/runtime/approval-runtime.js"
import { parseInlineApprovalIntent } from "@butler/runtime/inline-approval-intent.js"
import { parseCsvIds } from "./ilink-config.js"
import { resumeApprovedCapability } from "./approval-resume.js"
import { safeOwnerError } from "./safe-owner-error.js"
import { resolveOwnerSubject } from "./tool-boundary-helpers.js"
import type { ButlerLoopResult } from "./wechat-inbound-butler.js"
import type { Wiring } from "./wiring.js"

function canRespondToInlineApproval(
  fromUserId: string,
  pendingSubject: string,
  env: NodeJS.ProcessEnv,
): boolean {
  if (fromUserId === pendingSubject) return true
  const owner = resolveOwnerSubject(env, fromUserId)
  if (fromUserId === owner) return true
  return parseCsvIds(env["BUTLER_OWNER_WECHAT_ID"]).includes(fromUserId)
}

/**
 * Handle WeChat inline approval replies ("确认" / "拒绝") before starting a
 * new inbound Run. Returns null when the message is not an approval intent.
 */
export async function tryWechatInlineApproval(args: {
  readonly wiring: Wiring
  readonly conversationId: string
  readonly content: string
  readonly fromUserId: string
  readonly env?: NodeJS.ProcessEnv
}): Promise<ButlerLoopResult | null> {
  const env = args.env ?? process.env
  const intent = parseInlineApprovalIntent(args.content)
  if (!intent) return null

  const pendingSteps = await args.wiring.runtimeStore.listWaitingApprovalStepsForConversation(
    args.conversationId,
  )
  const step = pendingSteps.at(-1)
  if (!step) {
    return {
      // D63 T2 (audit #9 F-02/F-03): unify the no-pending reply and add a
      // recovery hint. Previously `可拒绝的待审批操作` was awkward
      // (redundant modifier), and both branches lacked a recovery hint.
      reply:
        intent === "approve" || intent === "deny"
          ? "当前对话没有待审批的操作，直接发送你的请求即可。"
          : "当前对话没有待审批的操作，直接发送你的请求即可。",
      iterations: 0,
      toolCalls: 0,
      finalDecision: "Respond",
      traces: ["inline-approval: no pending step"],
    }
  }

  // D67 T1b — fatigue-checklist step uses a different step.input shape
  // ({ reason: "fatigue_checklist", toolName, items }) than the runtime's
  // PendingCapabilityInput. Bridge here: ack the owner, mark step succeeded,
  // and skip resumeApprovedCapability (no real capability to resume — the
  // fatigue checklist only blocks execution; tool execution was already
  // completed at the original Run, and a re-dispatch is owned by the
  // approval-resume handler for the next turn if needed).
  const pending = parsePendingCapabilityInput(step.input)
  const fatigueInput = step.input as
    | { readonly reason?: unknown; readonly toolName?: unknown }
    | undefined
  if (
    pending === null &&
    fatigueInput !== undefined &&
    fatigueInput["reason"] === "fatigue_checklist"
  ) {
    const toolName =
      typeof fatigueInput["toolName"] === "string"
        ? fatigueInput["toolName"]
        : "操作"
    if (intent === "deny") {
      await args.wiring.runtimeStore.updateStep({
        stepId: step.id,
        status: "failed",
        output: { deniedBy: args.fromUserId, reason: "fatigue_checklist_denied" },
        updatedAt: new Date(),
      })
      return {
        reply: `已升级拒绝（${toolName}），操作不会执行。`,
        iterations: 0,
        toolCalls: 0,
        finalDecision: "Respond",
        traces: [`inline-approval: fatigue checklist deny ${step.id}`],
      }
    }
    await args.wiring.runtimeStore.updateStep({
      stepId: step.id,
      status: "succeeded",
      output: {
        approvedBy: args.fromUserId,
        reason: "fatigue_checklist_ack",
        toolName,
      },
      updatedAt: new Date(),
    })
    return {
      // D48 owner-jargon: contains "已升级" + "确认" per F2 acceptance.
      reply: `已升级确认（${toolName}），操作将按你之前的请求执行。`,
      iterations: 0,
      toolCalls: 0,
      finalDecision: "Respond",
      traces: [`inline-approval: fatigue checklist ack ${step.id}`],
    }
  }
  const pendingCapability = pending
  if (!pendingCapability) {
    return {
      reply: "待审批步骤数据无效，请联系管理员处理。",
      iterations: 0,
      toolCalls: 0,
      finalDecision: "Finish",
      traces: ["inline-approval: invalid pending payload"],
    }
  }

  if (!canRespondToInlineApproval(args.fromUserId, pendingCapability.subject, env)) {
    return {
      reply: "你没有权限批准或拒绝此操作。",
      iterations: 0,
      toolCalls: 0,
      finalDecision: "Finish",
      traces: ["inline-approval: unauthorized subject"],
    }
  }

  if (intent === "deny") {
    const deny = await denyWaitingStep(args.wiring.runtimeStore, step.id, args.fromUserId)
    return {
      // D60 T2.6 (audit #3 F-10): drop raw capability name (write_file, etc.)
      // from owner-facing reply. Operator tool id, not catalog id.
      reply: deny.alreadyProcessed
        ? "该操作已处理，无需重复操作。"
        : "已拒绝待审批操作。",
      iterations: 0,
      toolCalls: 0,
      finalDecision: "Finish",
      traces: [`inline-approval: denied ${step.id} (capability=${pendingCapability.capability})`],
    }
  }

  try {
    const decision = await approveWaitingStep(
      args.wiring.runtimeStore,
      step.id,
      args.fromUserId,
    )
    if (decision._tag === "alreadyProcessed") {
      return {
        reply: "该操作已处理，无需重复审批。",
        iterations: 0,
        toolCalls: 0,
        finalDecision: "Finish",
        traces: [`inline-approval: already processed ${step.id}`],
      }
    }
    const resumed = await resumeApprovedCapability(args.wiring, decision, { env })
    if (resumed.ok) {
      return {
        reply: String(resumed.output),
        iterations: 1,
        toolCalls: 1,
        finalDecision: "Respond",
        traces: [`inline-approval: approved ${step.id}`],
      }
    }
    return {
      reply: safeOwnerError(
        new Error(`resumeApprovedCapability returned not-ok: ${resumed.reason}`),
        "审批后执行失败，请稍后重试",
        {
          operation: "inline-approval-resume",
          stepId: step.id,
          reason: resumed.reason,
        },
      ),
      iterations: 1,
      toolCalls: 1,
      finalDecision: "Finish",
      traces: [`inline-approval: resume failed ${resumed.reason}`],
    }
  } catch (err) {
    return {
      reply: safeOwnerError(err, "审批失败，请稍后重试", {
        operation: "inline-approval-approve",
        stepId: step.id,
      }),
      iterations: 0,
      toolCalls: 0,
      finalDecision: "Finish",
      traces: ["inline-approval: approve error"],
    }
  }
}

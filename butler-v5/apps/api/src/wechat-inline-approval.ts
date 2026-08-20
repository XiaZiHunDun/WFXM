import {
  approveWaitingStep,
  denyWaitingStep,
  parsePendingCapabilityInput,
} from "@butler/runtime/approval-runtime.js"
import { parseInlineApprovalIntent } from "@butler/runtime/inline-approval-intent.js"
import { parseCsvIds } from "./ilink-config.js"
import { resumeApprovedCapability } from "./approval-resume.js"
import { resolveOwnerSubject } from "./tool-boundary.js"
import type { ButlerLoopResult } from "./wechat-inbound-butler.js"
import type { Wiring } from "./wiring.js"

export function canRespondToInlineApproval(
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
      reply:
        intent === "approve"
          ? "当前对话没有待审批的操作。"
          : "当前对话没有可拒绝的待审批操作。",
      iterations: 0,
      toolCalls: 0,
      finalDecision: "Respond",
      traces: ["inline-approval: no pending step"],
    }
  }

  const pending = parsePendingCapabilityInput(step.input)
  if (!pending) {
    return {
      reply: "待审批步骤数据无效，请联系管理员处理。",
      iterations: 0,
      toolCalls: 0,
      finalDecision: "Finish",
      traces: ["inline-approval: invalid pending payload"],
    }
  }

  if (!canRespondToInlineApproval(args.fromUserId, pending.subject, env)) {
    return {
      reply: "你没有权限批准或拒绝此操作。",
      iterations: 0,
      toolCalls: 0,
      finalDecision: "Finish",
      traces: ["inline-approval: unauthorized subject"],
    }
  }

  if (intent === "deny") {
    await denyWaitingStep(args.wiring.runtimeStore, step.id, args.fromUserId)
    return {
      reply: `已拒绝待审批操作（${pending.capability}）。`,
      iterations: 0,
      toolCalls: 0,
      finalDecision: "Finish",
      traces: [`inline-approval: denied ${step.id}`],
    }
  }

  try {
    const decision = await approveWaitingStep(
      args.wiring.runtimeStore,
      step.id,
      args.fromUserId,
    )
    const resumed = await resumeApprovedCapability(args.wiring, decision, env)
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
      reply: `[审批后执行失败] ${resumed.reason}`,
      iterations: 1,
      toolCalls: 1,
      finalDecision: "Finish",
      traces: [`inline-approval: resume failed ${resumed.reason}`],
    }
  } catch (err) {
    return {
      reply: `[审批失败] ${err instanceof Error ? err.message : String(err)}`,
      iterations: 0,
      toolCalls: 0,
      finalDecision: "Finish",
      traces: ["inline-approval: approve error"],
    }
  }
}

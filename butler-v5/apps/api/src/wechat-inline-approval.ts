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
      // D63 T2 (audit #9 F-04): add recovery hint to unauthorized branch.
      // Tells owner what they can try next instead of a dead-end reply.
      reply: "你没有权限批准或拒绝此操作。如需处理，请联系管理员或确认是否登录了正确的微信账号。",
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
      // D63 T1 (audit #9 F-06): include the publicResource path so owner
      // can connect the deny reply to which pending step they just acted
      // on. Generic "已拒绝待审批操作" was ambiguous when multiple pending
      // steps existed in conversation history.
      reply: deny.alreadyProcessed
        ? "该操作已处理，无需重复操作。"
        : `✅ 已拒绝：${pending.resource}`,
      iterations: 0,
      toolCalls: 0,
      finalDecision: "Finish",
      traces: [`inline-approval: denied ${step.id} (capability=${pending.capability})`],
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
        // D63 T1 (audit #9 F-05): add `✅ 已批准` acknowledgement prefix
        // so owner sees the approval was processed (not just the tool's
        // raw output). The ack + the tool output together let owner
        // connect the approval action to the result.
        reply: `✅ 已批准：${pending.resource}\n\n${String(resumed.output)}`,
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

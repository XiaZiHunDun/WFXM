/**
 * Butler Runtime inbound glue for the channel adapters.
 *
 * Keeps the legacy `runButlerLoop` pipeline untouched: the composition root
 * injects a `ButlerRuntime`, this module maps an inbound message (or an
 * interactive-card callback) onto it and delivers the reply through the
 * existing ChannelPort.
 */
import type { ButlerRuntime, ButlerTurnResult } from "@butler/runtime/butler/butler-runtime.js"
import { parseApprovalPayload } from "@butler/runtime/butler/approval-notice.js"
import { splitForWechat } from "@butler/runtime/butler/presentation.js"
import type { ChannelPort, ChannelRecipient } from "@butler/ports/core/channel.js"

export interface ButlerInboundInput {
  readonly conversationId: string
  readonly userId: string
  readonly projectId?: string
  readonly content: string
  /** Task awaiting approval in this conversation; enables 确认 / 拒绝 rules. */
  readonly activeTaskId?: string
  /** Card button payload (`approve:<taskId>` / `reject:<taskId>`). */
  readonly approvalPayload?: string
}

export interface ButlerInboundResult {
  readonly result: ButlerTurnResult
  readonly sent: boolean
  readonly sendError?: string
}

export interface ButlerSendResult {
  readonly sent: boolean
  readonly sendError?: string
}

export async function handleButlerInbound(args: {
  readonly butler: ButlerRuntime
  readonly channel: ChannelPort
  readonly recipient: ChannelRecipient
  readonly input: ButlerInboundInput
}): Promise<ButlerInboundResult> {
  const { butler, channel, recipient, input } = args
  const result = input.approvalPayload
    ? await resolveApproval(butler, input)
    : await butler.handle({
        conversationId: input.conversationId,
        userId: input.userId,
        ...(input.projectId === undefined ? {} : { projectId: input.projectId }),
        content: input.content,
        ...(input.activeTaskId === undefined ? {} : { activeTaskId: input.activeTaskId }),
      })

  const delivery = await deliver(channel, recipient, result.reply)
  return {
    result,
    ...(delivery.sent ? { sent: true } : { sent: false }),
    ...(delivery.sendError === undefined ? {} : { sendError: delivery.sendError }),
  }
}

/**
 * Proactive path for detached tasks: after the owner's task pauses, poll this
 * to push the approval prompt without waiting for another inbound message.
 */
export async function notifyApprovalIfPaused(args: {
  readonly butler: ButlerRuntime
  readonly channel: ChannelPort
  readonly recipient: ChannelRecipient
  readonly taskId: string
}): Promise<ButlerSendResult | null> {
  const notice = await args.butler.approvalNotice(args.taskId)
  if (!notice) return null
  return deliver(args.channel, args.recipient, notice.text)
}

async function resolveApproval(
  butler: ButlerRuntime,
  input: ButlerInboundInput,
): Promise<ButlerTurnResult> {
  const intent = parseApprovalPayload({
    ...(input.approvalPayload === undefined ? {} : { payload: input.approvalPayload }),
    ...(input.activeTaskId === undefined ? {} : { activeTaskId: input.activeTaskId }),
  })
  if (!intent) {
    throw new Error(`invalid approval payload: ${input.approvalPayload ?? ""}`)
  }
  return butler.handleApprovalCallback({
    conversationId: input.conversationId,
    userId: input.userId,
    taskId: intent.taskId,
    approved: intent.approved,
  })
}

async function deliver(
  channel: ChannelPort,
  recipient: ChannelRecipient,
  content: string,
): Promise<ButlerSendResult> {
  const parts = splitForWechat(content)
  if (parts.length === 0) return { sent: false, sendError: "empty reply" }
  try {
    for (const part of parts) {
      const sent = await channel.sendText({ recipient, content: part })
      if (!sent.ok) return { sent: false, sendError: sent.reason }
    }
    return { sent: true }
  } catch (error) {
    return {
      sent: false,
      sendError: error instanceof Error ? error.message : String(error),
    }
  }
}

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
import { finalizeReply, splitForWechat } from "@butler/runtime/butler/presentation.js"
import type { ButlerTaskRef } from "@butler/ports/core/butler-task.js"
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

interface ButlerSendResult {
  readonly sent: boolean
  readonly sendError?: string
}

export interface TaskSettledPushInput<TOwner = string> {
  readonly owner: TOwner
  readonly text: string
}

export type TaskSettledPushResult =
  { readonly ok: true } | { readonly ok: false; readonly reason: string }

/** Owner-facing copy for a detached task that finished without a prompt. */
export function formatTaskSettledNotice(ref: ButlerTaskRef): string {
  if (ref.status === "paused" || ref.status === "running") return ""
  const failed = ref.status === "failed"
  const header = failed ? "【任务失败】" : "【任务完成】"
  const title = ref.summary?.trim().slice(0, 60) ?? ""
  const detail = (failed ? ref.error : ref.lastReply)?.trim().slice(0, 400) ?? ""
  return [
    `${header}${ref.taskId.slice(0, 8)} ${title}`.trim(),
    ...(detail.length === 0 ? [] : [failed ? `原因：${detail}` : `结果：${detail}`]),
  ].join("\n")
}

/**
 * Turns detached-task settle events into one push. Missing owner mapping or a
 * task that already carries no notice is skipped rather than guessed.
 */
export function createTaskSettledNotifier<TOwner = string>(args: {
  readonly approvalNotice: (taskId: string) => Promise<{ readonly text: string } | null>
  readonly resolveOwner: (conversationId: string) => TOwner | undefined
  readonly push: (input: TaskSettledPushInput<TOwner>) => Promise<TaskSettledPushResult>
  readonly logger?: { warn(message: string, extra?: unknown): void }
}): (ref: ButlerTaskRef) => Promise<void> {
  const logger = args.logger ?? {
    warn: (message: string, extra?: unknown) => {
      // eslint-disable-next-line no-console -- operator-facing warning
      console.warn(message, extra ?? "")
    },
  }
  return async (ref: ButlerTaskRef): Promise<void> => {
    const conversationId = ref.conversationId
    if (conversationId === undefined) return
    const owner = args.resolveOwner(conversationId)
    if (owner === undefined) return
    if (typeof owner === "string" && owner.trim().length === 0) return
    const notice = ref.status === "paused" ? await args.approvalNotice(ref.taskId) : null
    const text = (notice?.text ?? formatTaskSettledNotice(ref)).trim()
    if (text.length === 0) return
    try {
      const result = await args.push({ owner, text })
      if (!result.ok) logger.warn(`[butler] ${ref.taskId} proactive push failed`, result.reason)
    } catch (error) {
      logger.warn(`[butler] ${ref.taskId} proactive push threw`, error)
    }
  }
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
  // Project memory on a cadence; a slow or failing summary never blocks the reply.
  void butler.summarizeIfDue(input.conversationId).catch(() => undefined)
  return {
    result,
    ...(delivery.sent ? { sent: true } : { sent: false }),
    ...(delivery.sendError === undefined ? {} : { sendError: delivery.sendError }),
  }
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
  const parts = splitForWechat(finalizeReply(content))
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

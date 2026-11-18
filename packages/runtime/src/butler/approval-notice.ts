/**
 * Approval notices and card callbacks.
 *
 * Transport-neutral: the WeChat adapter renders `text` for a plain message and
 * may map `actions[].payload` onto interactive-card buttons. Both directions
 * end up in `ButlerRuntime.handleApprovalCallback` via `parseApprovalPayload`.
 */
import type { ButlerTaskRef } from "@butler/ports/core/butler-task.js"
import { toolActionLabel } from "./presentation.js"

export interface ButlerApprovalAction {
  readonly id: "approve" | "reject"
  readonly label: string
  /** Opaque string a card button sends back, e.g. `approve:task-1`. */
  readonly payload: string
}

export interface ButlerApprovalNotice {
  readonly taskId: string
  readonly title: string
  readonly text: string
  readonly actions: readonly ButlerApprovalAction[]
}

export interface ButlerApprovalIntent {
  readonly taskId: string
  readonly approved: boolean
}

export function buildApprovalNotice(task: ButlerTaskRef): ButlerApprovalNotice | null {
  const pending = task.pending
  if (!pending || task.status !== "paused") return null

  const title = `任务 ${task.taskId} 需要确认`
  const text = [
    title,
    ...(task.summary === undefined ? [] : [`目标：${task.summary}`]),
    `待执行：${toolActionLabel(pending.toolName)}`,
    `原因：${pending.reason}`,
    "回复「确认」继续，或「拒绝」取消。",
  ].join("\n")

  return {
    taskId: task.taskId,
    title,
    text,
    actions: [
      { id: "approve", label: "确认", payload: `approve:${task.taskId}` },
      { id: "reject", label: "拒绝", payload: `reject:${task.taskId}` },
    ],
  }
}

/**
 * Parses a card callback payload (`approve:<taskId>` / `reject:<taskId>`) or a
 * bare action id together with the active task.
 */
export function parseApprovalPayload(input: {
  readonly payload?: string
  readonly action?: string
  readonly activeTaskId?: string
}): ButlerApprovalIntent | null {
  if (input.payload) {
    const match = /^(approve|reject):(.+)$/.exec(input.payload.trim())
    if (match) {
      return { taskId: match[2] as string, approved: match[1] === "approve" }
    }
  }
  if ((input.action === "approve" || input.action === "reject") && input.activeTaskId) {
    return { taskId: input.activeTaskId, approved: input.action === "approve" }
  }
  return null
}

/**
 * Butler rule router.
 *
 * Deterministic intents (help / status / task list / new task / approval) are
 * answered without a model call. Anything that misses falls through to the
 * butler Agent. Rules only match explicit commands, never free-form prose.
 */

export const BUTLER_HELP_TEXT = [
  "可用指令：",
  "/help 查看帮助",
  "/status 查看当前任务",
  "/tasks 列出项目任务",
  "/new <目标> 创建任务",
  "确认 / 拒绝 处理任务审批",
].join("\n")

export type ButlerRuleAction =
  | { readonly kind: "reply"; readonly name: string; readonly reply: string }
  | { readonly kind: "list_tasks"; readonly name: string }
  | { readonly kind: "task_status"; readonly name: string; readonly taskId: string }
  | { readonly kind: "start_task"; readonly name: string; readonly goal: string }
  | {
      readonly kind: "approve"
      readonly name: string
      readonly taskId: string
      readonly approved: boolean
    }

export interface ButlerRuleInput {
  readonly content: string
  readonly activeTaskId?: string
}

const APPROVE_WORDS = new Set(["确认", "同意", "通过", "approve"])
const REJECT_WORDS = new Set(["拒绝", "不同意", "reject"])

export function matchButlerRule(input: ButlerRuleInput): ButlerRuleAction | null {
  const text = input.content.trim()
  if (!text) return null
  const lower = text.toLowerCase()

  if (lower === "/help" || lower === "help" || text === "帮助" || text === "?" || text === "？") {
    return { kind: "reply", name: "help", reply: BUTLER_HELP_TEXT }
  }

  if (lower === "/status" || text === "状态" || text === "进度") {
    const taskId = input.activeTaskId
    return taskId
      ? { kind: "task_status", name: "status", taskId }
      : { kind: "list_tasks", name: "status" }
  }

  if (lower === "/tasks" || text === "任务列表" || text === "任务") {
    return { kind: "list_tasks", name: "tasks" }
  }

  const newMatch = /^\/(?:new|task)\s+(.+)$/i.exec(text) ?? /^(?:新任务|新建任务)[:：\s]*(.+)$/.exec(text)
  const goal = newMatch?.[1]?.trim()
  if (goal) return { kind: "start_task", name: "new", goal }

  if (lower === "/new" || text === "新任务" || text === "新建任务") {
    return { kind: "reply", name: "new-usage", reply: "用法：/new <目标>，例如 /new 修复登录超时" }
  }

  const taskId = input.activeTaskId
  if (taskId && (APPROVE_WORDS.has(lower) || APPROVE_WORDS.has(text))) {
    return { kind: "approve", name: "approve", taskId, approved: true }
  }
  if (taskId && (REJECT_WORDS.has(lower) || REJECT_WORDS.has(text))) {
    return { kind: "approve", name: "reject", taskId, approved: false }
  }

  return null
}

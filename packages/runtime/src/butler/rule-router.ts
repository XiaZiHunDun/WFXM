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
  "/status [任务ID] 查看任务，缺省看当前任务",
  "/tasks 列出项目任务",
  "/new <目标> 创建任务",
  "/retry [任务ID] 重试失败或中断的任务",
  "/diagnose 诊断当前会话与任务状态",
  "/undo 查看撤销边界（不支持自动撤销）",
  "/project [项目ID] 查看或切换项目",
  "/remember <内容> 记住一条长期信息",
  "确认 / 拒绝 处理任务审批",
].join("\n")

export type ButlerRuleAction =
  | { readonly kind: "reply"; readonly name: string; readonly reply: string }
  | { readonly kind: "list_tasks"; readonly name: string }
  | { readonly kind: "task_status"; readonly name: string; readonly taskId: string }
  | { readonly kind: "start_task"; readonly name: string; readonly goal: string }
  | { readonly kind: "remember"; readonly name: string; readonly text: string }
  | { readonly kind: "project"; readonly name: string; readonly projectId?: string }
  | { readonly kind: "retry"; readonly name: string; readonly taskId?: string }
  | { readonly kind: "diagnose"; readonly name: string }
  | { readonly kind: "undo"; readonly name: string }
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
const RETRY_WORDS = new Set(["重试", "重试刚才", "重试上次", "重试上一个任务", "重试任务"])
const DIAGNOSE_WORDS = new Set(["诊断", "诊断一下"])
const UNDO_WORDS = new Set(["撤销", "撤销刚才", "撤销上一步"])

/** Bare approval words; the runtime resolves the task from the conversation. */
export function matchApprovalWord(content: string): { approved: boolean } | null {
  const text = content.trim()
  const lower = text.toLowerCase()
  if (APPROVE_WORDS.has(lower) || APPROVE_WORDS.has(text)) return { approved: true }
  if (REJECT_WORDS.has(lower) || REJECT_WORDS.has(text)) return { approved: false }
  return null
}

export function matchButlerRule(input: ButlerRuleInput): ButlerRuleAction | null {
  const text = input.content.trim()
  if (!text) return null
  const lower = text.toLowerCase()

  if (lower === "/help" || lower === "help" || text === "帮助" || text === "?" || text === "？") {
    return { kind: "reply", name: "help", reply: BUTLER_HELP_TEXT }
  }

  const projectMatch = /^\/project(?:\s+(\S+))?$/i.exec(text)
  if (projectMatch) {
    const target = projectMatch[1]?.trim()
    return target === undefined
      ? { kind: "project", name: "project" }
      : { kind: "project", name: "project", projectId: target }
  }

  const switchMatch = /^(?:切换项目|项目)[:：]?\s+(.+)$/.exec(text)
  const switchTarget = switchMatch?.[1]?.trim()
  if (switchTarget) return { kind: "project", name: "project", projectId: switchTarget }

  if (text === "项目") return { kind: "project", name: "project" }

  const rememberMatch =
    /^\/(?:remember|记住)\s+(.+)$/i.exec(text) ?? /^记住[:：]\s*(.+)$/.exec(text)
  const remembered = rememberMatch?.[1]?.trim()
  if (remembered) return { kind: "remember", name: "remember", text: remembered }

  if (lower === "/remember" || lower === "/记住") {
    return {
      kind: "reply",
      name: "remember-usage",
      reply: "用法：/remember <要记住的内容>，例如 /remember 我偏好先结论后细节",
    }
  }

  const statusMatch = /^\/status(?:\s+(\S+))?$/i.exec(text)
  if (statusMatch) {
    const taskId = statusMatch[1]?.trim() ?? input.activeTaskId
    return taskId
      ? { kind: "task_status", name: "status", taskId }
      : { kind: "list_tasks", name: "status" }
  }

  if (text === "状态" || text === "进度") {
    const taskId = input.activeTaskId
    return taskId
      ? { kind: "task_status", name: "status", taskId }
      : { kind: "list_tasks", name: "status" }
  }

  if (lower === "/tasks" || text === "任务列表" || text === "任务") {
    return { kind: "list_tasks", name: "tasks" }
  }

  const newMatch =
    /^\/(?:new|task)\s+(.+)$/i.exec(text) ?? /^(?:新任务|新建任务)[:：\s]*(.+)$/.exec(text)
  const goal = newMatch?.[1]?.trim()
  if (goal) return { kind: "start_task", name: "new", goal }

  if (lower === "/new" || text === "新任务" || text === "新建任务") {
    return { kind: "reply", name: "new-usage", reply: "用法：/new <目标>，例如 /new 修复登录超时" }
  }

  const retryMatch = /^\/retry(?:\s+(\S+))?$/i.exec(text)
  if (retryMatch) {
    const target = retryMatch[1]?.trim()
    return target === undefined
      ? { kind: "retry", name: "retry" }
      : { kind: "retry", name: "retry", taskId: target }
  }

  if (RETRY_WORDS.has(text)) return { kind: "retry", name: "retry" }

  if (lower === "/diagnose" || DIAGNOSE_WORDS.has(text)) {
    return { kind: "diagnose", name: "diagnose" }
  }

  if (lower === "/undo" || UNDO_WORDS.has(text)) {
    return { kind: "undo", name: "undo" }
  }

  const taskId = input.activeTaskId
  const intent = matchApprovalWord(text)
  if (taskId && intent) {
    return {
      kind: "approve",
      name: intent.approved ? "approve" : "reject",
      taskId,
      approved: intent.approved,
    }
  }

  return null
}

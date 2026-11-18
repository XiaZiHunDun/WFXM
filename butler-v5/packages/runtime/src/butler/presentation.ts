/**
 * Single exit for butler text that a user will read on WeChat.
 *
 * WeChat renders plain text only: no markdown, no code fences, and it truncates
 * very long messages. Every user-visible string goes through this module so the
 * wording and formatting rules are testable in one place instead of being
 * scattered across the rule router, the runtime and the approval notice.
 */
export const MAX_WECHAT_MESSAGE_CHARS = 1800

/** Hard cap before a reply is truncated; the transport splits below this. */
export const MAX_REPLY_CHARS = 8000

const FALLBACK_REPLY = "我没有生成有效回复，请重试或换个说法。"

const TOOL_ACTION_LABELS: Readonly<Record<string, string>> = {
  read: "读取文件",
  write: "修改文件",
  edit: "修改文件",
  bash: "执行命令",
  grep: "搜索内容",
  find: "查找文件",
  ls: "查看目录",
  start_task: "创建任务",
  status: "查询任务",
}

const TASK_STATUS_LABELS: Readonly<Record<string, string>> = {
  idle: "待命",
  running: "执行中",
  paused: "等待确认",
  closed: "已结束",
  failed: "失败",
}

/** Turns a raw pi tool name into a human action label. */
export function toolActionLabel(name: string): string {
  return TOOL_ACTION_LABELS[name] ?? "执行操作"
}

/** Turns a task status into user-facing Chinese. */
export function taskStatusLabel(status: string): string {
  return TASK_STATUS_LABELS[status] ?? status
}

/**
 * Removes markdown that WeChat would show literally. Code content is kept;
 * only the markers go away. Conservative on purpose: `__name__`-style Python
 * identifiers survive because only complete `__x__` pairs are unwrapped.
 */
export function sanitizeForWechat(text: string): string {
  let value = text.replace(/\r\n/g, "\n")
  value = value.replace(/```[^\n]*\n([\s\S]*?)```/g, "$1")
  value = value.replace(/```/g, "")
  value = value.replace(/`([^`\n]+)`/g, "$1")
  value = value.replace(/\*\*([^*\n]+)\*\*/g, "$1")
  value = value.replace(/^#{1,6}\s+/gm, "")
  value = value.replace(/\n{3,}/g, "\n\n")
  return value.trim()
}

/**
 * Final pass for any reply before it leaves the runtime: sanitize, guarantee a
 * non-empty answer, and cap pathological lengths.
 */
export function finalizeReply(text: string): string {
  const clean = sanitizeForWechat(text)
  if (clean.length === 0) return FALLBACK_REPLY
  if (clean.length <= MAX_REPLY_CHARS) return clean
  return `${clean.slice(0, MAX_REPLY_CHARS)}\n……（内容较长，已截断）`
}

/**
 * Splits a final reply into WeChat-sized parts, preferring paragraph and line
 * boundaries so a sentence is not cut in half when a better boundary exists.
 */
export function splitForWechat(
  text: string,
  maxChars: number = MAX_WECHAT_MESSAGE_CHARS,
): readonly string[] {
  if (text.trim().length === 0) return []
  if (maxChars <= 0 || text.length <= maxChars) return [text]

  const parts: string[] = []
  let current = ""
  const flush = (): void => {
    const trimmed = current.trimEnd()
    if (trimmed.length > 0) parts.push(trimmed)
    current = ""
  }

  for (const line of text.split("\n")) {
    if (line.length > maxChars) {
      flush()
      for (let offset = 0; offset < line.length; offset += maxChars) {
        parts.push(line.slice(offset, offset + maxChars))
      }
      continue
    }
    const candidate = current.length === 0 ? line : `${current}\n${line}`
    if (candidate.length > maxChars) {
      flush()
      current = line
      continue
    }
    current = candidate
  }
  flush()
  return parts
}

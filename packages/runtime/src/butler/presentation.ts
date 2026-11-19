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
 * Internal vocabulary that leaks into model-written prose (tool outputs are
 * written in English for the model, and it echoes them). Map to the words an
 * owner actually uses; keep the patterns narrow so identifiers are untouched.
 */
const TERM_REPLACEMENTS: readonly (readonly [RegExp, string])[] = [
  [/[ \t]*\bexec\s*子代理/g, "执行代理"],
  [/[ \t]*执行子代理/g, "执行代理"],
  [/[ \t]*开发子代理/g, "开发代理"],
  // Any remaining "子代理" is still internal vocabulary to the owner.
  [/[ \t]*子代理/g, "执行代理"],
  [/[ \t]*\bDurable Memory\b/g, "长期记忆"],
  [/[ \t]*\bProject Knowledge\b/g, "项目知识"],
]

/**
 * F-08: raw tool ids that the model may echo. Only snake_case ids are mapped —
 * short English words such as `find`/`ls` can be legitimate prose.
 */
const TOOL_ID_LABELS: Readonly<Record<string, string>> = {
  read_file: "读取文件",
  list_dir: "查看目录",
  write_file: "修改文件",
  edit_file: "修改文件",
  apply_patch: "修改文件",
  delete_file: "删除文件",
  run_command: "执行命令",
  send_wechat_file: "发送文件",
  delegate_to_subagent: "委派子任务",
}

/** C0/C1 control characters are invisible or render as garbage on WeChat. */
// eslint-disable-next-line no-control-regex -- intentionally stripping C0/C1 controls
const CONTROL_CHARS = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]/g

/**
 * Removes markdown that WeChat would show literally. Code content is kept;
 * only the markers go away. Conservative on purpose: `__name__`-style Python
 * identifiers survive because only complete `__x__` pairs are unwrapped.
 */
export function sanitizeForWechat(text: string): string {
  let value = text.replace(/\r\n/g, "\n").replace(CONTROL_CHARS, "")
  for (const [pattern, replacement] of TERM_REPLACEMENTS) {
    value = value.replace(pattern, replacement)
  }
  value = value.replace(/\bmcp_[A-Za-z0-9_.-]+\b/g, "外部工具")
  value = value.replace(
    /\b(read_file|list_dir|write_file|edit_file|apply_patch|delete_file|run_command|send_wechat_file|delegate_to_subagent)\b/g,
    (name: string) => TOOL_ID_LABELS[name] ?? name,
  )
  value = value.replace(/```[^\n]*\n([\s\S]*?)```/g, "$1")
  value = value.replace(/```/g, "")
  value = value.replace(/`([^`\n]+)`/g, "$1")
  value = value.replace(/\*\*([^*\n]+)\*\*/g, "$1")
  value = value.replace(/^#{1,6}\s+/gm, "")
  value = value.replace(/^\s*-{3,}\s*$/gm, "")
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
      // F-07: never slice between a high/low surrogate pair; joining the parts
      // must reproduce the original text exactly.
      let offset = 0
      while (offset < line.length) {
        let end = Math.min(offset + maxChars, line.length)
        if (end < line.length) {
          const last = line.charCodeAt(end - 1)
          if (last >= 0xd800 && last <= 0xdbff) end -= 1
          if (end === offset) end = Math.min(offset + maxChars + 1, line.length)
        }
        parts.push(line.slice(offset, end))
        offset = end
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

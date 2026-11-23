/**
 * Owner-facing approval preview (C2). Pure: no IO, no policy, no state.
 *
 * `write_file` → relative path + a compact line diff against the previous
 * content; `run_command` → the full argv. Anything else returns null so the
 * caller keeps the legacy wording.
 */

export interface ApprovalPreviewInput {
  readonly capability: string
  readonly args: Readonly<Record<string, unknown>>
  /** Previous file content; null/"" means "new file", undefined means unknown. */
  readonly oldContent?: string | null
  readonly workspaceRoot?: string
  readonly maxLines?: number
  readonly maxChars?: number
}

const DEFAULT_MAX_LINES = 12
const DEFAULT_MAX_CHARS = 800
const MAX_COMMAND_CHARS = 600

function normalizeSlashes(value: string): string {
  return value.replace(/\\/g, "/")
}

/** Never expose absolute paths: strip the workspace prefix or keep basename. */
export function previewPath(path: string, workspaceRoot?: string): string {
  const value = normalizeSlashes(path.trim())
  if (!value) return value
  const root = workspaceRoot === undefined ? "" : normalizeSlashes(workspaceRoot.trim())
  if (root && value.startsWith(`${root.replace(/\/$/, "")}/`)) {
    return value.slice(root.replace(/\/$/, "").length + 1)
  }
  if (value.startsWith("/") || /^[A-Za-z]:\//.test(value)) {
    const parts = value.split("/").filter((part) => part.length > 0)
    return parts.at(-1) ?? "项目目录"
  }
  return value
}

function commandLine(args: Readonly<Record<string, unknown>>): string | null {
  const argv = args["argv"]
  if (!Array.isArray(argv)) return null
  const joined = argv
    .map((part) => String(part))
    .join(" ")
    // eslint-disable-next-line no-control-regex -- collapse control chars in a one-line preview
    .replace(/[\u0000-\u001F\u007F]+/g, " ")
    .trim()
  if (!joined) return null
  if (joined.length <= MAX_COMMAND_CHARS) return `命令：${joined}`
  return `命令：${joined.slice(0, MAX_COMMAND_CHARS)}…（已截断）`
}

function splitLines(text: string): readonly string[] {
  return text.length === 0 ? [] : text.split("\n")
}

interface LineDiff {
  readonly added: readonly string[]
  readonly removed: readonly string[]
}

function diffLines(oldText: string, newText: string): LineDiff {
  const oldLines = splitLines(oldText)
  const newLines = splitLines(newText)
  let prefix = 0
  while (
    prefix < oldLines.length &&
    prefix < newLines.length &&
    oldLines[prefix] === newLines[prefix]
  ) {
    prefix += 1
  }
  let suffix = 0
  while (
    suffix < oldLines.length - prefix &&
    suffix < newLines.length - prefix &&
    oldLines[oldLines.length - 1 - suffix] === newLines[newLines.length - 1 - suffix]
  ) {
    suffix += 1
  }
  return {
    added: newLines.slice(prefix, newLines.length - suffix),
    removed: oldLines.slice(prefix, oldLines.length - suffix),
  }
}

function writeFilePreview(input: ApprovalPreviewInput): string | null {
  const path = typeof input.args["path"] === "string" ? input.args["path"] : ""
  const content = typeof input.args["content"] === "string" ? input.args["content"] : null
  if (!path.trim() || content === null) return null

  const relative = previewPath(path, input.workspaceRoot)
  if (input.oldContent === undefined) {
    const lineCount = splitLines(content).length
    return `文件：${relative}\n将写入 ${lineCount} 行`
  }
  const diff = diffLines(input.oldContent ?? "", content)
  const header = `文件：${relative}\n新增 ${diff.added.length} 行，删除 ${diff.removed.length} 行`
  if (diff.added.length === 0 && diff.removed.length === 0) return header

  const maxLines = input.maxLines ?? DEFAULT_MAX_LINES
  const lines: string[] = []
  for (const line of diff.removed) {
    lines.push(`- ${line}`)
    if (lines.length >= maxLines) break
  }
  if (lines.length < maxLines) {
    for (const line of diff.added) {
      lines.push(`+ ${line}`)
      if (lines.length >= maxLines) break
    }
  }
  const total = diff.removed.length + diff.added.length
  const truncated = total > lines.length
  const body = `${header}\n${lines.join("\n")}${truncated ? "\n…（已截断）" : ""}`
  const maxChars = input.maxChars ?? DEFAULT_MAX_CHARS
  return body.length <= maxChars ? body : `${body.slice(0, maxChars)}…（已截断）`
}

/** Owner-readable preview, or null when this capability has none. */
export function renderApprovalPreview(input: ApprovalPreviewInput): string | null {
  const capability = input.capability.trim()
  if (capability === "run_command") return commandLine(input.args)
  if (capability === "write_file") return writeFilePreview(input)
  return null
}

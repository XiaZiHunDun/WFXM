// infrastructure/patch/relative-indenter.ts
// 多策略 Patch 应用 [OPT-13] — unified diff / search-replace / 相对缩进

// ─── 多策略 Patch 应用 ──────────────────────────────────
export function applyPatch(content: string, patch: string): string {
  // 1. 尝试 unified diff
  if (patch.startsWith("@@")) return applyUnified(content, patch)
  // 2. 尝试 search-replace
  if (patch.includes("<<<<<<< SEARCH")) return applySearchReplace(content, patch)
  // 3. 兜底：相对缩进插入
  return applyRelativeIndent(content, patch)
}

// ─── Unified Diff 应用 ──────────────────────────────────
function applyUnified(content: string, patch: string): string {
  const lines = content.split("\n")
  const chunks = patch.split("\n")
  const result: string[] = []
  let lineIdx = 0

  for (const chunk of chunks) {
    if (chunk.startsWith("@@")) {
      const match = chunk.match(/@@ -(\d+),\d+ \+(\d+),\d+ @@/)
      if (match && match[2]) {
        lineIdx = parseInt(match[2], 10) - 1
      }
      continue
    }
    if (chunk.startsWith("+")) {
      result.push(chunk.slice(1))
      lineIdx++
    } else if (chunk.startsWith("-")) {
      lineIdx++
    } else if (chunk.startsWith(" ")) {
      // Context line: push if exists, advance index
      if (lineIdx < lines.length) {
        const line = lines[lineIdx]
        if (line) result.push(line)
      }
      lineIdx++
    }
  }

  return result.join("\n")
}

// ─── Search/Replace 应用 ────────────────────────────────
function applySearchReplace(content: string, patch: string): string {
  const searchMatch = patch.match(/<<<<<<< SEARCH\n([\s\S]*?)=======/)
  const replaceMatch = patch.match(/=======\n([\s\S]*?)>>>>>>> REPLACE/)
  if (searchMatch && searchMatch[1] && replaceMatch && replaceMatch[1]) {
    return content.replace(searchMatch[1].trim(), replaceMatch[1].trim())
  }
  return content
}

// ─── 相对缩进插入 ───────────────────────────────────────
function applyRelativeIndent(content: string, patch: string): string {
  const lines = content.split("\n")
  const patchLines = patch.split("\n")

  // 检测缩进级别
  let indentLevel = 0
  for (const line of lines) {
    const match = line.match(/^(\s*)/)
    if (match && match[1] && match[1].length > 0) {
      indentLevel = match[1].length
      break
    }
  }

  const indent = " ".repeat(indentLevel)
  const indented = patchLines.map((line) => (line.trim() ? indent + line : line))

  return [...lines, ...indented].join("\n")
}

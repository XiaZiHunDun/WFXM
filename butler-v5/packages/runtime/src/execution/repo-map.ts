import { readdir, readFile } from "node:fs/promises"
import { extname, join, relative } from "node:path"

export interface RepoMapOptions {
  readonly maxDepth?: number
  readonly maxFiles?: number
  readonly maxChars?: number
  readonly maxSymbolsPerFile?: number
}

const DEFAULT_MAX_DEPTH = 3
const DEFAULT_MAX_FILES = 200
const DEFAULT_MAX_CHARS = 2_500
const DEFAULT_MAX_SYMBOLS_PER_FILE = 6
const MAX_FILE_BYTES = 64_000

const SKIP_DIRS = new Set([
  "node_modules",
  "dist",
  "build",
  "out",
  "coverage",
  ".next",
  ".turbo",
  ".pnpm-store",
  "vendor",
  "__pycache__",
  ".venv",
  "target",
])

const CODE_EXTS = new Set([
  ".ts",
  ".tsx",
  ".js",
  ".jsx",
  ".mjs",
  ".cjs",
  ".py",
  ".go",
  ".rs",
  ".java",
  ".kt",
  ".rb",
  ".php",
  ".cs",
  ".swift",
  ".md",
])

const SYMBOL_PATTERNS: readonly RegExp[] = [
  /^export\s+(?:declare\s+)?(?:async\s+)?(?:function|class|const|let|interface|type|enum)\s+([A-Za-z0-9_$]+)/,
  /^(?:async\s+)?(?:function|class)\s+([A-Za-z0-9_$]+)/,
  /^def\s+([A-Za-z_][A-Za-z0-9_]*)/,
  /^type\s+([A-Za-z_][A-Za-z0-9_]*)\s+struct\b/,
  /^func\s+(?:\([^)]*\)\s*)?([A-Za-z_][A-Za-z0-9_]*)/,
  /^type\s+([A-Za-z_][A-Za-z0-9_]*)\s+(?:interface|struct)\b/,
]

interface WalkState {
  readonly root: string
  readonly paths: string[]
  readonly maxDepth: number
  readonly maxFiles: number
}

async function collectFiles(state: WalkState, dir: string, depth: number): Promise<void> {
  if (depth > state.maxDepth || state.paths.length >= state.maxFiles) return
  let entries
  try {
    entries = await readdir(dir, { withFileTypes: true })
  } catch {
    return
  }
  entries.sort((left, right) => left.name.localeCompare(right.name))
  for (const entry of entries) {
    if (state.paths.length >= state.maxFiles) return
    if (entry.name.startsWith(".")) continue
    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name)) continue
      await collectFiles(state, join(dir, entry.name), depth + 1)
      continue
    }
    if (!entry.isFile()) continue
    if (!CODE_EXTS.has(extname(entry.name))) continue
    state.paths.push(relative(state.root, join(dir, entry.name)))
  }
}

async function fileSymbols(path: string, maxSymbols: number): Promise<readonly string[]> {
  let text: string
  try {
    text = await readFile(path, "utf8")
  } catch {
    return []
  }
  const symbols: string[] = []
  for (const line of text.slice(0, MAX_FILE_BYTES).split("\n")) {
    for (const pattern of SYMBOL_PATTERNS) {
      const match = pattern.exec(line)
      if (!match?.[1]) continue
      if (!symbols.includes(match[1])) symbols.push(match[1])
      break
    }
    if (symbols.length >= maxSymbols) return symbols
  }
  return symbols
}

/**
 * Compact repository outline for the task-layer system prompt: file paths plus
 * a few top-level/exported symbols per file. This is deliberately not a full
 * AST index — it only tells the agent where things live, so it can then use
 * read/grep/find for the exact source.
 */
export async function buildRepoMap(root: string, options: RepoMapOptions = {}): Promise<string> {
  const state: WalkState = {
    root,
    paths: [],
    maxDepth: options.maxDepth ?? DEFAULT_MAX_DEPTH,
    maxFiles: options.maxFiles ?? DEFAULT_MAX_FILES,
  }
  await collectFiles(state, root, 0)
  if (state.paths.length === 0) return ""

  const maxChars = options.maxChars ?? DEFAULT_MAX_CHARS
  const maxSymbols = options.maxSymbolsPerFile ?? DEFAULT_MAX_SYMBOLS_PER_FILE
  const lines: string[] = []
  let used = 0
  for (const path of state.paths) {
    const symbols = await fileSymbols(join(root, path), maxSymbols)
    const line = symbols.length === 0 ? `- ${path}` : `- ${path}: ${symbols.join(", ")}`
    if (used + line.length + 1 > maxChars) break
    lines.push(line)
    used += line.length + 1
  }
  if (lines.length === 0) return ""
  return `仓库地图（自动生成，只列路径与少量符号，源码需用 read/grep 查看）：\n${lines.join("\n")}`
}

/**
 * P4.1 native pi tools for the task layer.
 *
 * These are intentionally pi-shaped (`read/write/edit/bash/grep/find/ls`) and
 * independent from the butler capability facade. Every path stays inside the
 * task workspace; expected failures are returned as `isError` results so pi can
 * feed them back to the model without aborting the run.
 */
import { spawn } from "node:child_process"
import { mkdir, lstat, readdir, readFile, realpath, stat, writeFile } from "node:fs/promises"
import { dirname, isAbsolute, relative, resolve } from "node:path"
import type { AgentTool, AgentToolResult } from "@butler/pi-agent"

export interface PiNativeToolOptions {
  readonly cwd: string
  readonly maxReadBytes?: number
  readonly maxWriteBytes?: number
  readonly maxOutputBytes?: number
  readonly timeoutMs?: number
  readonly env?: NodeJS.ProcessEnv
}

const DEFAULT_MAX_READ_BYTES = 64 * 1024
const DEFAULT_MAX_WRITE_BYTES = 64 * 1024
const DEFAULT_MAX_OUTPUT_BYTES = 32 * 1024
const DEFAULT_TIMEOUT_MS = 60_000
const MAX_READ_LINES = 2_000
const MAX_SEARCH_RESULTS = 200
const MAX_SCAN_ENTRIES = 20_000
const SKIP_DIRS = new Set(["node_modules", ".git", "dist", ".turbo", "coverage"])

const SAFE_ENV_KEYS = ["PATH", "HOME", "LANG", "LC_ALL", "NODE_ENV", "TERM", "TMPDIR"] as const

export type ResolvePathResult =
  { readonly ok: true; readonly path: string } | { readonly ok: false; readonly reason: string }

function escapesRoot(rootReal: string, candidate: string): boolean {
  const rel = relative(rootReal, candidate)
  return rel.startsWith("..") || isAbsolute(rel)
}

async function pathExists(path: string): Promise<boolean> {
  try {
    // lstat, not stat: a dangling symlink must count as an existing component
    // so its target gets resolved and rejected instead of written through.
    await lstat(path)
    return true
  } catch {
    return false
  }
}

/**
 * Resolve `requested` so the result stays inside `root`.
 *
 * Existing targets are checked through `realpath` so symlinks cannot escape.
 * For new files we walk up to the nearest existing ancestor and verify it too.
 */
export async function resolveInsideWorkspace(
  root: string,
  requested: string,
): Promise<ResolvePathResult> {
  const trimmed = requested.trim()
  if (!trimmed) return { ok: false, reason: "path is required" }

  let rootReal: string
  try {
    rootReal = await realpath(root)
  } catch (error) {
    return {
      ok: false,
      reason: `workspace root is not readable: ${error instanceof Error ? error.message : String(error)}`,
    }
  }

  const abs = isAbsolute(trimmed) ? resolve(trimmed) : resolve(rootReal, trimmed)
  if (escapesRoot(rootReal, abs)) return { ok: false, reason: "path is outside the workspace" }

  let existing = abs
  while (!(await pathExists(existing))) {
    const parent = dirname(existing)
    if (parent === existing) break
    existing = parent
  }
  try {
    const real = await realpath(existing)
    if (escapesRoot(rootReal, real)) {
      return { ok: false, reason: "path is outside the workspace" }
    }
    if (existing === abs) return { ok: true, path: real }
  } catch (error) {
    // Fail closed: a component exists but cannot be resolved (dangling symlink,
    // permission error). Falling back to the lexical path could write through
    // a symlink that points outside the workspace.
    return {
      ok: false,
      reason: `cannot resolve path inside the workspace: ${error instanceof Error ? error.message : String(error)}`,
    }
  }
  return { ok: true, path: abs }
}

function textResult(
  text: string,
  details: Record<string, unknown>,
  isError = false,
): AgentToolResult<Record<string, unknown>> {
  return {
    content: [{ type: "text", text }],
    details: { ...details, isError },
    isError,
  }
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function safeEnv(source?: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {}
  for (const key of SAFE_ENV_KEYS) {
    const value = process.env[key]
    if (value !== undefined) env[key] = value
  }
  for (const [key, value] of Object.entries(source ?? {})) {
    if (value !== undefined) env[key] = value
  }
  return env
}

interface WalkEntry {
  readonly abs: string
  readonly rel: string
  readonly kind: "file" | "dir"
}

async function walk(
  root: string,
  start: string,
  visit: (entry: WalkEntry) => Promise<boolean | void> | boolean | void,
): Promise<void> {
  let scanned = 0
  const stack: string[] = [start]
  while (stack.length > 0) {
    const dir = stack.pop()
    if (!dir) continue
    let entries
    try {
      entries = await readdir(dir, { withFileTypes: true })
    } catch {
      continue
    }
    for (const entry of entries) {
      scanned += 1
      if (scanned > MAX_SCAN_ENTRIES) return
      const abs = resolve(dir, entry.name)
      const rel = relative(root, abs)
      if (entry.isSymbolicLink()) continue
      if (entry.isDirectory()) {
        if (SKIP_DIRS.has(entry.name)) continue
        const stop = await visit({ abs, rel, kind: "dir" })
        if (stop === true) return
        stack.push(abs)
      } else if (entry.isFile()) {
        const stop = await visit({ abs, rel, kind: "file" })
        if (stop === true) return
      }
    }
  }
}

function globToRegExp(glob: string): RegExp {
  let pattern = ""
  for (let i = 0; i < glob.length; i += 1) {
    const char = glob[i] ?? ""
    if (char === "*") {
      if (glob[i + 1] === "*") {
        pattern += ".*"
        i += 1
      } else {
        pattern += "[^/]*"
      }
    } else if (char === "?") {
      pattern += "[^/]"
    } else {
      pattern += char.replace(/[.+^${}()|[\]\\]/g, "\\$&")
    }
  }
  return new RegExp(`^${pattern}$`)
}

function makeReadTool(cwd: string, maxBytes: number): AgentTool {
  return {
    name: "read",
    label: "read",
    description: "Read a text file inside the workspace with line numbers.",
    parameters: {
      type: "object",
      properties: {
        path: { type: "string", description: "Workspace-relative file path" },
        offset: { type: "number", description: "1-based first line to return" },
        limit: { type: "number", description: "Maximum number of lines" },
      },
      required: ["path"],
    },
    execute: async (_id, raw) => {
      const params = raw as { path?: unknown; offset?: unknown; limit?: unknown }
      if (typeof params.path !== "string") {
        return textResult("[error] path is required", { tool: "read" }, true)
      }
      const resolved = await resolveInsideWorkspace(cwd, params.path)
      if (!resolved.ok) return textResult(`[error] ${resolved.reason}`, { tool: "read" }, true)
      try {
        const info = await stat(resolved.path)
        if (!info.isFile()) return textResult("[error] path is not a file", { tool: "read" }, true)
        if (info.size > maxBytes) {
          return textResult(`[error] file exceeds ${maxBytes} bytes`, { tool: "read" }, true)
        }
        const buffer = await readFile(resolved.path)
        if (buffer.includes(0)) {
          return textResult("[error] refusing binary file", { tool: "read" }, true)
        }
        const lines = buffer.toString("utf8").split("\n")
        const offset =
          typeof params.offset === "number" && params.offset > 0 ? Math.floor(params.offset) : 1
        const limit =
          typeof params.limit === "number" && params.limit > 0
            ? Math.min(Math.floor(params.limit), MAX_READ_LINES)
            : MAX_READ_LINES
        const slice = lines.slice(offset - 1, offset - 1 + limit)
        // F-11: a truly empty file must read as "(empty file)", not as a
        // numbered blank line invented by "".split("\n").
        const text =
          buffer.byteLength === 0
            ? "(empty file)"
            : slice
                .map((line, index) => `${String(offset + index).padStart(6, " ")} | ${line}`)
                .join("\n") || "(empty file)"
        return textResult(text, {
          tool: "read",
          path: resolved.path,
          lines: slice.length,
          bytes: buffer.byteLength,
        })
      } catch (error) {
        return textResult(`[error] ${errorText(error)}`, { tool: "read" }, true)
      }
    },
  }
}

function makeWriteTool(cwd: string, maxBytes: number): AgentTool {
  return {
    name: "write",
    label: "write",
    description: "Create or overwrite a text file inside the workspace.",
    parameters: {
      type: "object",
      properties: {
        path: { type: "string", description: "Workspace-relative file path" },
        content: { type: "string", description: "Full file content" },
      },
      required: ["path", "content"],
    },
    execute: async (_id, raw) => {
      const params = raw as { path?: unknown; content?: unknown }
      if (typeof params.path !== "string") {
        return textResult("[error] path is required", { tool: "write" }, true)
      }
      if (typeof params.content !== "string") {
        return textResult("[error] content is required", { tool: "write" }, true)
      }
      if (Buffer.byteLength(params.content, "utf8") > maxBytes) {
        return textResult(`[error] content exceeds ${maxBytes} bytes`, { tool: "write" }, true)
      }
      if (params.content.includes("\0")) {
        return textResult("[error] refusing binary content", { tool: "write" }, true)
      }
      const resolved = await resolveInsideWorkspace(cwd, params.path)
      if (!resolved.ok) return textResult(`[error] ${resolved.reason}`, { tool: "write" }, true)
      try {
        await mkdir(dirname(resolved.path), { recursive: true })
        await writeFile(resolved.path, params.content, "utf8")
        return textResult(`wrote ${params.path.trim()} (${params.content.length} chars)`, {
          tool: "write",
          path: resolved.path,
          bytes: Buffer.byteLength(params.content, "utf8"),
        })
      } catch (error) {
        return textResult(`[error] ${errorText(error)}`, { tool: "write" }, true)
      }
    },
  }
}

function makeEditTool(cwd: string, maxBytes: number): AgentTool {
  return {
    name: "edit",
    label: "edit",
    description: "Replace an exact text fragment in a workspace file.",
    parameters: {
      type: "object",
      properties: {
        path: { type: "string", description: "Workspace-relative file path" },
        oldText: { type: "string", description: "Exact text to replace" },
        newText: { type: "string", description: "Replacement text" },
        replaceAll: { type: "boolean", description: "Replace every occurrence" },
      },
      required: ["path", "oldText", "newText"],
    },
    execute: async (_id, raw) => {
      const params = raw as {
        path?: unknown
        oldText?: unknown
        newText?: unknown
        replaceAll?: unknown
      }
      if (typeof params.path !== "string") {
        return textResult("[error] path is required", { tool: "edit" }, true)
      }
      if (typeof params.oldText !== "string" || params.oldText.length === 0) {
        return textResult("[error] oldText is required", { tool: "edit" }, true)
      }
      if (typeof params.newText !== "string") {
        return textResult("[error] newText is required", { tool: "edit" }, true)
      }
      const resolved = await resolveInsideWorkspace(cwd, params.path)
      if (!resolved.ok) return textResult(`[error] ${resolved.reason}`, { tool: "edit" }, true)
      try {
        const info = await stat(resolved.path)
        if (!info.isFile()) return textResult("[error] path is not a file", { tool: "edit" }, true)
        if (info.size > maxBytes) {
          return textResult(`[error] file exceeds ${maxBytes} bytes`, { tool: "edit" }, true)
        }
        const before = await readFile(resolved.path, "utf8")
        const occurrences = before.split(params.oldText).length - 1
        if (occurrences === 0) {
          return textResult("[error] oldText was not found", { tool: "edit" }, true)
        }
        if (occurrences > 1 && params.replaceAll !== true) {
          return textResult(
            `[error] oldText matched ${occurrences} times; pass replaceAll or provide more context`,
            { tool: "edit" },
            true,
          )
        }
        const after =
          params.replaceAll === true
            ? before.split(params.oldText).join(params.newText)
            : before.replace(params.oldText, params.newText)
        await writeFile(resolved.path, after, "utf8")
        return textResult(`edited ${params.path.trim()} (${occurrences} replacement(s))`, {
          tool: "edit",
          path: resolved.path,
          replacements: params.replaceAll === true ? occurrences : 1,
        })
      } catch (error) {
        return textResult(`[error] ${errorText(error)}`, { tool: "edit" }, true)
      }
    },
  }
}

function makeBashTool(
  cwd: string,
  maxOutputBytes: number,
  timeoutMs: number,
  env?: NodeJS.ProcessEnv,
): AgentTool {
  return {
    name: "bash",
    label: "bash",
    description: "Run a shell command inside the workspace and return combined output.",
    parameters: {
      type: "object",
      properties: {
        command: { type: "string", description: "Shell command to run" },
        timeoutMs: { type: "number", description: "Optional timeout in milliseconds" },
      },
      required: ["command"],
    },
    execute: async (_id, raw, signal) => {
      const params = raw as { command?: unknown; timeoutMs?: unknown }
      if (typeof params.command !== "string" || params.command.trim().length === 0) {
        return textResult("[error] command is required", { tool: "bash" }, true)
      }
      const limit =
        typeof params.timeoutMs === "number" && params.timeoutMs > 0
          ? Math.min(Math.floor(params.timeoutMs), 300_000)
          : timeoutMs
      return new Promise<AgentToolResult<Record<string, unknown>>>((resolvePromise) => {
        const started = Date.now()
        let settled = false
        let output = ""
        let truncated = false
        const child = spawn("bash", ["-lc", params.command as string], {
          cwd,
          env: safeEnv(env),
          stdio: ["ignore", "pipe", "pipe"],
        })
        const finish = (exitCode: number | null, reason?: string): void => {
          if (settled) return
          settled = true
          clearTimeout(timer)
          signal?.removeEventListener("abort", onAbort)
          const suffix = truncated ? `\n…(truncated at ${maxOutputBytes} bytes)` : ""
          const body = output + suffix
          const details = { tool: "bash", cwd, exitCode, durationMs: Date.now() - started }
          if (exitCode === 0) {
            resolvePromise(textResult(body || "(no output)", details))
          } else {
            resolvePromise(
              textResult(
                `[exit ${exitCode ?? "null"}] ${(reason ?? body) || "(no output)"}`,
                details,
                true,
              ),
            )
          }
        }
        const append = (chunk: Buffer): void => {
          if (output.length >= maxOutputBytes) {
            truncated = true
            return
          }
          output += chunk.toString()
          if (output.length > maxOutputBytes) {
            output = output.slice(0, maxOutputBytes)
            truncated = true
          }
        }
        const onAbort = (): void => {
          child.kill("SIGKILL")
          // Resolve immediately; waiting for "close" can hang when the shell
          // spawned grandchildren that keep the pipes open.
          finish(null, "aborted")
        }
        // Declared before the process listeners so every async finish path has
        // an initialized handle; callbacks never run during this synchronous block.
        const timer = setTimeout(() => {
          child.kill("SIGKILL")
          finish(null, `timeout after ${limit}ms`)
        }, limit)
        child.stdout.on("data", append)
        child.stderr.on("data", append)
        child.on("error", (error) => finish(null, error.message))
        child.on("close", (code) => finish(code))
        if (signal?.aborted) {
          onAbort()
          return
        }
        signal?.addEventListener("abort", onAbort, { once: true })
      })
    },
  }
}

function makeGrepTool(cwd: string): AgentTool {
  return {
    name: "grep",
    label: "grep",
    description: "Search text files inside the workspace and return path:line matches.",
    parameters: {
      type: "object",
      properties: {
        pattern: { type: "string", description: "Regular expression" },
        path: { type: "string", description: "Optional directory or file to search" },
        glob: { type: "string", description: "Optional filename glob filter" },
      },
      required: ["pattern"],
    },
    execute: async (_id, raw) => {
      const params = raw as { pattern?: unknown; path?: unknown; glob?: unknown }
      if (typeof params.pattern !== "string" || params.pattern.length === 0) {
        return textResult("[error] pattern is required", { tool: "grep" }, true)
      }
      let matcher: RegExp
      try {
        matcher = new RegExp(params.pattern)
      } catch (error) {
        return textResult(`[error] invalid pattern: ${errorText(error)}`, { tool: "grep" }, true)
      }
      const globFilter =
        typeof params.glob === "string" && params.glob.length > 0
          ? globToRegExp(params.glob)
          : undefined
      const start =
        typeof params.path === "string" && params.path.trim().length > 0
          ? await resolveInsideWorkspace(cwd, params.path)
          : ({ ok: true, path: cwd } as const)
      if (!start.ok) return textResult(`[error] ${start.reason}`, { tool: "grep" }, true)

      const hits: string[] = []
      try {
        await walk(cwd, start.path, async (entry) => {
          if (entry.kind !== "file") return
          if (globFilter && !globFilter.test(entry.rel)) return
          const info = await stat(entry.abs).catch(() => undefined)
          if (!info || info.size > 1024 * 1024) return
          const buffer = await readFile(entry.abs).catch(() => undefined)
          if (!buffer || buffer.includes(0)) return
          const lines = buffer.toString("utf8").split("\n")
          for (let index = 0; index < lines.length; index += 1) {
            if (matcher.test(lines[index] ?? "")) {
              hits.push(`${entry.rel}:${index + 1}:${lines[index] ?? ""}`)
              if (hits.length >= MAX_SEARCH_RESULTS) return true
            }
          }
          return
        })
      } catch (error) {
        return textResult(`[error] ${errorText(error)}`, { tool: "grep" }, true)
      }
      return textResult(hits.length > 0 ? hits.join("\n") : "no matches", {
        tool: "grep",
        matches: hits.length,
      })
    },
  }
}

function makeFindTool(cwd: string): AgentTool {
  return {
    name: "find",
    label: "find",
    description: "Find workspace files whose relative path matches a glob.",
    parameters: {
      type: "object",
      properties: {
        pattern: { type: "string", description: "Glob such as **/*.ts" },
        path: { type: "string", description: "Optional directory to search" },
      },
      required: ["pattern"],
    },
    execute: async (_id, raw) => {
      const params = raw as { pattern?: unknown; path?: unknown }
      if (typeof params.pattern !== "string" || params.pattern.length === 0) {
        return textResult("[error] pattern is required", { tool: "find" }, true)
      }
      const matcher = globToRegExp(params.pattern)
      const start =
        typeof params.path === "string" && params.path.trim().length > 0
          ? await resolveInsideWorkspace(cwd, params.path)
          : ({ ok: true, path: cwd } as const)
      if (!start.ok) return textResult(`[error] ${start.reason}`, { tool: "find" }, true)

      const hits: string[] = []
      await walk(cwd, start.path, (entry) => {
        if (entry.kind !== "file") return
        if (!matcher.test(entry.rel)) return
        hits.push(entry.rel)
        if (hits.length >= MAX_SEARCH_RESULTS) return true
        return
      })
      hits.sort()
      return textResult(hits.length > 0 ? hits.join("\n") : "no files", {
        tool: "find",
        matches: hits.length,
      })
    },
  }
}

function makeLsTool(cwd: string): AgentTool {
  return {
    name: "ls",
    label: "ls",
    description: "List a directory inside the workspace.",
    parameters: {
      type: "object",
      properties: {
        path: { type: "string", description: "Optional directory path" },
      },
    },
    execute: async (_id, raw) => {
      const params = raw as { path?: unknown }
      const requested = typeof params.path === "string" ? params.path : "."
      const resolved = await resolveInsideWorkspace(cwd, requested)
      if (!resolved.ok) return textResult(`[error] ${resolved.reason}`, { tool: "ls" }, true)
      try {
        const entries = await readdir(resolved.path, { withFileTypes: true })
        const lines = await Promise.all(
          entries
            .sort((a, b) => a.name.localeCompare(b.name))
            .map(async (entry) => {
              if (entry.isDirectory()) return `d ${entry.name}`
              const info = await stat(resolve(resolved.path, entry.name)).catch(() => undefined)
              return `f ${entry.name} ${info?.size ?? 0}`
            }),
        )
        return textResult(lines.length > 0 ? lines.join("\n") : "(empty directory)", {
          tool: "ls",
          path: resolved.path,
          entries: lines.length,
        })
      } catch (error) {
        return textResult(`[error] ${errorText(error)}`, { tool: "ls" }, true)
      }
    },
  }
}

/** Build the seven pi-native tools bound to one workspace. */
export function createPiNativeTools(options: PiNativeToolOptions): AgentTool[] {
  const cwd = resolve(options.cwd)
  const maxReadBytes = options.maxReadBytes ?? DEFAULT_MAX_READ_BYTES
  const maxWriteBytes = options.maxWriteBytes ?? DEFAULT_MAX_WRITE_BYTES
  const maxOutputBytes = options.maxOutputBytes ?? DEFAULT_MAX_OUTPUT_BYTES
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS
  return [
    makeReadTool(cwd, maxReadBytes),
    makeWriteTool(cwd, maxWriteBytes),
    makeEditTool(cwd, maxWriteBytes),
    makeBashTool(cwd, maxOutputBytes, timeoutMs, options.env),
    makeGrepTool(cwd),
    makeFindTool(cwd),
    makeLsTool(cwd),
  ]
}

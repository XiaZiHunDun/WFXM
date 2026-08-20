/**
 * R8.x.12 — sandboxed `read_file` and `run_command` for the wechat butler.
 *
 * Both tools stay inside a workspace root (ctx.workspaceRoot, else
 * `run_command` never uses a shell: argv[0] must be on a closed
 * allowlist (R8.x.20: also rg/grep, python3, pnpm, node), args cannot
 * contain `..` or start with `/`.
 *
 * Failures return `{ ok: false, reason }` — no throw.
 */
import { spawn } from "node:child_process"
import { readFileSync, realpathSync, statSync } from "node:fs"
import { isAbsolute, relative, resolve } from "node:path"
import type { ToolDefinition } from "@butler/runtime/tool-runtime.js"

export const ALLOWED_RUN_COMMANDS = [
  "cat",
  "date",
  "echo",
  "git",
  "grep",
  "head",
  "ls",
  "node",
  "pnpm",
  "pwd",
  "python3",
  "rg",
  "wc",
] as const

const MAX_READ_BYTES = 64 * 1024
const MAX_COMMAND_OUTPUT_BYTES = 32 * 1024

export interface WorkspaceToolContext {
  readonly workspaceRoot?: string
}

export type ResolvePathResult =
  { readonly ok: true; readonly path: string } | { readonly ok: false; readonly reason: string }

export function workspaceRootFrom(ctx?: WorkspaceToolContext): string {
  const fromCtx = ctx?.workspaceRoot?.trim()
  if (fromCtx) return fromCtx
  const fromEnv = process.env["BUTLER_V5_WORKSPACE_ROOT"]?.trim()
  if (fromEnv) return fromEnv
  return process.cwd()
}

/**
 * Resolve `requested` so the result is always a real path inside `root`.
 * Symlinks that escape the root are rejected.
 */
export function resolveUnderWorkspace(root: string, requested: string): ResolvePathResult {
  const trimmed = requested.trim()
  if (!trimmed) return { ok: false, reason: "path is required" }
  let rootReal: string
  try {
    rootReal = realpathSync(root)
  } catch (err) {
    return {
      ok: false,
      reason: `workspace root is not readable: ${err instanceof Error ? err.message : String(err)}`,
    }
  }
  const abs = isAbsolute(trimmed) ? trimmed : resolve(rootReal, trimmed)
  if (escapesRoot(rootReal, abs)) {
    return { ok: false, reason: "path is outside the workspace" }
  }
  try {
    const real = realpathSync(abs)
    if (escapesRoot(rootReal, real)) {
      return { ok: false, reason: "path is outside the workspace" }
    }
    return { ok: true, path: real }
  } catch {
    return { ok: true, path: abs }
  }
}

function escapesRoot(rootReal: string, candidate: string): boolean {
  const rel = relative(rootReal, candidate)
  return rel.startsWith("..") || isAbsolute(rel)
}

export function makeReadFileTool(ctx: WorkspaceToolContext = {}): ToolDefinition {
  return {
    name: "read_file" as ToolDefinition["name"],
    risk: "low",
    async run(
      args: Record<string, unknown>,
    ): Promise<
      | { readonly ok: true; readonly output: unknown }
      | { readonly ok: false; readonly reason: string }
    > {
      const raw = args["path"]
      if (typeof raw !== "string") return { ok: false, reason: "path is required" }
      const resolved = resolveUnderWorkspace(workspaceRootFrom(ctx), raw)
      if (!resolved.ok) return resolved
      try {
        const st = statSync(resolved.path)
        if (!st.isFile()) return { ok: false, reason: "path is not a file" }
        if (st.size > MAX_READ_BYTES) {
          return { ok: false, reason: `file exceeds ${MAX_READ_BYTES} bytes` }
        }
        const buf = readFileSync(resolved.path)
        if (buf.includes(0)) return { ok: false, reason: "refusing binary file" }
        return { ok: true, output: buf.toString("utf8") }
      } catch (err) {
        return { ok: false, reason: err instanceof Error ? err.message : String(err) }
      }
    },
  }
}

export function makeRunCommandTool(ctx: WorkspaceToolContext = {}): ToolDefinition {
  return {
    name: "run_command" as ToolDefinition["name"],
    risk: "high",
    async run(
      args: Record<string, unknown>,
      signal?: AbortSignal,
    ): Promise<
      | { readonly ok: true; readonly output: unknown }
      | { readonly ok: false; readonly reason: string }
    > {
      const argvRaw = args["argv"]
      if (!Array.isArray(argvRaw) || argvRaw.length === 0) {
        return { ok: false, reason: "argv is required (non-empty string array)" }
      }
      const argv: string[] = []
      for (const a of argvRaw) {
        if (typeof a !== "string" || a.length === 0) {
          return { ok: false, reason: "argv entries must be non-empty strings" }
        }
        argv.push(a)
      }
      const program = argv[0] ?? ""
      if (program.includes("/") || program.includes("\\")) {
        return { ok: false, reason: "program must be a bare command name" }
      }
      const allowed = new Set<string>(ALLOWED_RUN_COMMANDS)
      if (!allowed.has(program)) {
        return {
          ok: false,
          reason: `command not allowed: ${program} (allowed: ${ALLOWED_RUN_COMMANDS.join(", ")})`,
        }
      }
      for (const a of argv.slice(1)) {
        if (a.includes("..") || a.startsWith("/")) {
          return { ok: false, reason: `arg is outside the workspace: ${a}` }
        }
      }
      const cwd = workspaceRootFrom(ctx)
      return await spawnCaptured(argv, cwd, signal)
    },
  }
}

function spawnCaptured(
  argv: readonly string[],
  cwd: string,
  signal?: AbortSignal,
): Promise<
  { readonly ok: true; readonly output: unknown } | { readonly ok: false; readonly reason: string }
> {
  const program = argv[0]
  if (!program) return Promise.resolve({ ok: false, reason: "argv is required" })
  return new Promise((resolvePromise) => {
    if (signal?.aborted) {
      resolvePromise({ ok: false, reason: "aborted" })
      return
    }
    let child: ReturnType<typeof spawn>
    try {
      child = spawn(program, argv.slice(1), {
        cwd,
        env: { PATH: process.env["PATH"] ?? "/usr/bin:/bin" },
        stdio: ["ignore", "pipe", "pipe"],
      })
    } catch (err) {
      resolvePromise({
        ok: false,
        reason: err instanceof Error ? err.message : String(err),
      })
      return
    }
    const chunks: Buffer[] = []
    let total = 0
    const onAbort = () => {
      child.kill("SIGKILL")
    }
    signal?.addEventListener("abort", onAbort)
    const take = (buf: Buffer) => {
      total += buf.length
      if (total <= MAX_COMMAND_OUTPUT_BYTES) chunks.push(buf)
    }
    child.stdout?.on("data", (b: Buffer) => take(b))
    child.stderr?.on("data", (b: Buffer) => take(b))
    child.on("error", (err) => {
      signal?.removeEventListener("abort", onAbort)
      resolvePromise({ ok: false, reason: err.message })
    })
    child.on("close", (code) => {
      signal?.removeEventListener("abort", onAbort)
      const text = Buffer.concat(chunks).toString("utf8")
      const clipped =
        total > MAX_COMMAND_OUTPUT_BYTES
          ? `${text}\n…(truncated at ${MAX_COMMAND_OUTPUT_BYTES} bytes)`
          : text
      if (code !== 0) {
        resolvePromise({
          ok: false,
          reason: `exit ${code ?? "null"}: ${clipped.slice(0, 500)}`,
        })
        return
      }
      resolvePromise({ ok: true, output: clipped })
    })
  })
}

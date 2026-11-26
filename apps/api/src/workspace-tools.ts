/**
 * R8.x.12 — sandboxed `read_file`, `write_file`, and `run_command` for the wechat butler.
 *
 * Both tools stay inside a workspace root (ctx.workspaceRoot, else
 * `run_command` never uses a shell: argv[0] must be on a closed
 * allowlist (R8.x.20: also rg/grep, python3, pnpm, node), args cannot
 * contain `..` or start with `/`.
 *
 * Failures return `{ ok: false, reason }` — no throw.
 */
import { spawn } from "node:child_process"
import {
  mkdirSync,
  readdirSync,
  readFileSync,
  realpathSync,
  statSync,
  writeFileSync,
} from "node:fs"
import { dirname } from "node:path"
import { isAbsolute, relative, resolve } from "node:path"
import { makeToolName, type ToolDefinition } from "@butler/runtime/tool-runtime.js"
import type { CredentialProvider } from "@butler/ports/core/credential-provider.js"
import { isValidCredentialName } from "@butler/ports/core/credential-provider.js"
import {
  createHostCredentialProvider,
  injectRunCommandCredentials,
} from "@butler/adapters/credentials/host-credentials.js"
import { recordExecAudit, type ExecAuditContext } from "./exec-audit.js"
import { safeOwnerError } from "./safe-owner-error.js"
import { pushCommandToChain, recordWriteUndo } from "./workspace-tools-undo.js"

export const ALLOWED_RUN_COMMANDS = [
  "cat",
  "date",
  "echo",
  "find",
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

/**
 * Phase 7 fix F21: a 2,000-line TSX page (~82KB) could not be read whole or
 * edited at all — both tools hard-failed above 64KiB, so the child worked
 * around it by writing temporary patch scripts. read_file now reads large
 * files and truncates to the paging hint; edit_file caps the *result* at a
 * size that comfortably fits real source files.
 */
const MAX_READ_FILE_BYTES = 4 * 1024 * 1024
const MAX_WRITE_BYTES = 64 * 1024
const MAX_EDIT_RESULT_BYTES = 2 * 1024 * 1024
const MAX_COMMAND_OUTPUT_BYTES = 32 * 1024

/**
 * Phase 7 fix F16: a 5s budget killed `pnpm build` mid-run, so the child could
 * never verify its work. Package managers / builders / interpreters get the
 * long budget; everything else keeps the generic timeout. An explicit
 * `BUTLER_V5_RUN_COMMAND_TIMEOUT_MS` still wins in tool-boundary.
 */
export const BASE_RUN_COMMAND_TIMEOUT_MS = 5_000
export const LONG_RUNNING_COMMAND_TIMEOUT_MS = 120_000
const LONG_RUNNING_PROGRAMS: ReadonlySet<string> = new Set([
  "pnpm",
  "npm",
  "yarn",
  "npx",
  "next",
  "node",
  "python3",
])

export function resolveRunCommandDefaultTimeoutMs(argv: unknown): number {
  if (!Array.isArray(argv) || argv.length === 0) return BASE_RUN_COMMAND_TIMEOUT_MS
  const program = typeof argv[0] === "string" ? argv[0] : ""
  return LONG_RUNNING_PROGRAMS.has(program)
    ? LONG_RUNNING_COMMAND_TIMEOUT_MS
    : BASE_RUN_COMMAND_TIMEOUT_MS
}

export interface WorkspaceToolContext {
  readonly workspaceRoot?: string
  /** P2 host-injected credentials (defaults to env-backed host provider). */
  readonly credentialProvider?: CredentialProvider
  /** Names a run_command may inject (defaults to `BUTLER_V5_RUN_COMMAND_CREDENTIALS`). */
  readonly credentialAllowlist?: readonly string[]
  /** D47 exec audit context (observation only; injected from wiring). */
  readonly audit?: ExecAuditContext
  /** D49: chainId = runId (D47 ExecAuditContext.runId). */
  readonly chainId?: string
  /** D49: conversationId for chain↔conversation guard. */
  readonly conversationId?: string
}

/** Normalize `credentials`/`argv`-style name lists from tool args to valid names. */
function normalizeCredentialNames(raw: unknown): readonly string[] {
  if (!Array.isArray(raw)) return []
  const out: string[] = []
  for (const entry of raw) {
    if (typeof entry === "string" && isValidCredentialName(entry)) out.push(entry)
  }
  return out
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

/** Narrow workspace for bubblewrap+slirp runs (monorepo root bind can hang/fail). */
function sandboxWorkspaceRootFrom(ctx?: WorkspaceToolContext): string {
  const dedicated = process.env["BUTLER_V5_SANDBOX_WORKSPACE_ROOT"]?.trim()
  if (dedicated) return dedicated
  return workspaceRootFrom(ctx)
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

/**
 * Read-only directory listing for plan mode. Plan mode strips run_command /
 * write_file, which left `ls`-style questions with no tool and pushed the
 * model into delegating a one-second lookup (L4-2). This is listing only:
 * no shell, no writes, same workspace-escape guard as read_file.
 */
export function makeListDirTool(ctx: WorkspaceToolContext = {}): ToolDefinition {
  return {
    name: makeToolName("list_dir"),
    risk: "low",
    async run(
      args: Record<string, unknown>,
    ): Promise<
      | { readonly ok: true; readonly output: unknown }
      | { readonly ok: false; readonly reason: string }
    > {
      const raw = args["path"]
      const requested = typeof raw === "string" && raw.trim() ? raw.trim() : "."
      const resolved = resolveUnderWorkspace(workspaceRootFrom(ctx), requested)
      if (!resolved.ok) return resolved
      try {
        const entries = readdirSync(resolved.path, { withFileTypes: true })
          .filter((entry) => !entry.name.startsWith("."))
          .filter((entry) => entry.name !== "node_modules" && entry.name !== "dist")
          .sort(
            (a, b) =>
              Number(b.isDirectory()) - Number(a.isDirectory()) || a.name.localeCompare(b.name),
          )
        if (entries.length === 0) return { ok: true, output: "(empty)" }
        const shown = entries.slice(0, 200).map((entry) => {
          const kind = entry.isDirectory() ? "[目录] " : ""
          return `${kind}${entry.name}`
        })
        const suffix =
          entries.length > shown.length ? `\n…共 ${entries.length} 项，已省略后面部分` : ""
        return { ok: true, output: `${shown.join("\n")}${suffix}` }
      } catch (err) {
        return {
          ok: false,
          reason: `目录不可读：${err instanceof Error ? err.message : String(err)}`,
        }
      }
    },
  }
}

/**
 * Phase 7 fix F13: a 37KB source file read in one shot blew the child model's
 * context and the subagent died at iteration 1. read_file now supports
 * `offset`/`limit` (1-based lines) and caps inline output at 24KB, telling the
 * caller to page with offset/limit instead of dumping the whole file.
 */
const MAX_INLINE_READ_BYTES = 24 * 1024

function paginateReadOutput(text: string, args: Record<string, unknown>): string {
  const offsetRaw = args["offset"]
  const limitRaw = args["limit"]
  const offset =
    typeof offsetRaw === "number" && Number.isFinite(offsetRaw) && offsetRaw > 0
      ? Math.floor(offsetRaw)
      : 1
  const limit =
    typeof limitRaw === "number" && Number.isFinite(limitRaw) && limitRaw > 0
      ? Math.min(2000, Math.floor(limitRaw))
      : undefined
  if (
    offset === 1 &&
    limit === undefined &&
    Buffer.byteLength(text, "utf8") <= MAX_INLINE_READ_BYTES
  ) {
    return text
  }
  const lines = text.split("\n")
  const start = Math.min(offset - 1, lines.length)
  const end = limit === undefined ? lines.length : Math.min(start + limit, lines.length)
  const header = `[read_file] lines ${start + 1}-${end} of ${lines.length}`
  const body = lines.slice(start, end).join("\n")
  if (Buffer.byteLength(body, "utf8") <= MAX_INLINE_READ_BYTES) {
    return `${header}\n${body}`
  }
  const clipped = Buffer.from(body, "utf8")
    .subarray(0, MAX_INLINE_READ_BYTES)
    .toString("utf8")
  return `${header}\n${clipped}\n[read_file] 输出已截断（上限 ${MAX_INLINE_READ_BYTES} 字节）；请用 offset/limit 继续读取。`
}

export function makeReadFileTool(ctx: WorkspaceToolContext = {}): ToolDefinition {  return {
    name: makeToolName("read_file"),
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

      // R16 sandbox 扩面：当 BUTLER_V5_SANDBOX=bubblewrap 时，read_file 走
      // bwrap cat-equivalent（readOnly=true → workspace --ro-bind）。否则
      // fall back 到进程内 path-escape 约束（保持现状，避免 bwrap 不在的环境回退破坏）。
      const { executeArgvInSandbox, createDefaultProcessRunner } =
        await import("@butler/adapters/sandbox/bubblewrap-runner.js")
      const { currentNetworkAllowlist, currentSandboxProfileName } =
        await import("@butler/runtime/sandbox/index.js")
      const started = Date.now()
      const sandboxed = await executeArgvInSandbox({
        argv: ["cat", "--", resolved.path],
        workspaceRoot: sandboxWorkspaceRootFrom(ctx),
        readOnly: true,
        profileName: currentSandboxProfileName(),
        networkAllowlist: currentNetworkAllowlist(),
        env: process.env,
        runner: createDefaultProcessRunner(),
      })
      if ("mode" in sandboxed && sandboxed.mode === "disabled") {
        try {
          const st = statSync(resolved.path)
          if (!st.isFile()) return { ok: false, reason: "path is not a file" }
          if (st.size > MAX_READ_FILE_BYTES) {
            return {
              ok: false,
              reason: `file exceeds ${MAX_READ_FILE_BYTES} bytes（请用 run_command 分段读取，如 sed -n '1,200p' <path>）`,
            }
          }
          const buf = readFileSync(resolved.path)
          if (buf.includes(0)) return { ok: false, reason: "refusing binary file" }
          return { ok: true, output: paginateReadOutput(buf.toString("utf8"), args) }
        } catch (err) {
          // D69 T3 (audit #10 CQ-2): route raw ENOENT/EACCES messages through
          // safeOwnerError so the owner sees a Chinese fallback ("读取文件失败")
          // rather than `EACCES: permission denied, open '/etc/...'`. The
          // detailed error stays in operator logs via safeOwnerError.
          return {
            ok: false,
            reason: safeOwnerError(err, "读取文件失败", {
              operation: "read_file",
              path: resolved.path,
            }),
          }
        }
      } else {
        const result = sandboxed as {
          readonly ok: boolean
          readonly stdout?: string
          readonly stderr?: string
          readonly reason?: string
        }
        await recordExecAudit(ctx.audit, {
          cmd: ["cat", "--", resolved.path].join(" "),
          cwd: sandboxWorkspaceRootFrom(ctx),
          exit: null,
          durationMs: Date.now() - started,
          outcome: result.ok ? "ok" : "failed",
          detail: { tool: "read_file" },
        })
        if (!result.ok) return { ok: false, reason: result.reason ?? "sandbox failed" }
        return { ok: true, output: paginateReadOutput(result.stdout ?? "", args) }
      }
    },
  }
}

/**
 * Shared write path for `write_file` / `edit_file`: bwrap tee-equivalent when
 * the sandbox is enabled, in-process `writeFileSync` otherwise. Callers keep
 * their own validation + undo bookkeeping; this helper only performs I/O.
 */
async function writeTextToWorkspace(args: {
  readonly ctx: WorkspaceToolContext
  readonly resolvedPath: string
  readonly content: string
  readonly toolName: "write_file" | "edit_file"
}): Promise<{ readonly ok: true } | { readonly ok: false; readonly reason: string }> {
  const { executeArgvInSandbox } = await import("@butler/adapters/sandbox/bubblewrap-runner.js")
  const { currentNetworkAllowlist, currentSandboxProfileName } =
    await import("@butler/runtime/sandbox/index.js")
  const started = Date.now()
  const sandboxed = await executeArgvInSandbox({
    argv: ["tee", args.resolvedPath],
    workspaceRoot: sandboxWorkspaceRootFrom(args.ctx),
    profileName: currentSandboxProfileName(),
    networkAllowlist: currentNetworkAllowlist(),
    env: process.env,
    stdinContent: args.content,
  })
  if ("mode" in sandboxed && sandboxed.mode === "disabled") {
    try {
      mkdirSync(dirname(args.resolvedPath), { recursive: true })
      writeFileSync(args.resolvedPath, args.content, "utf8")
      return { ok: true }
    } catch (err) {
      return { ok: false, reason: err instanceof Error ? err.message : String(err) }
    }
  }
  const result = sandboxed as {
    readonly ok: boolean
    readonly stdout?: string
    readonly stderr?: string
    readonly reason?: string
  }
  await recordExecAudit(args.ctx.audit, {
    cmd: ["tee", args.resolvedPath].join(" "),
    cwd: sandboxWorkspaceRootFrom(args.ctx),
    exit: null,
    durationMs: Date.now() - started,
    outcome: result.ok ? "ok" : "failed",
    detail: { tool: args.toolName },
  })
  if (!result.ok) return { ok: false, reason: result.reason ?? "sandbox failed" }
  return { ok: true }
}

export function makeWriteFileTool(ctx: WorkspaceToolContext = {}): ToolDefinition {
  return {
    name: makeToolName("write_file"),
    risk: "high",
    async run(
      args: Record<string, unknown>,
    ): Promise<
      | { readonly ok: true; readonly output: unknown }
      | { readonly ok: false; readonly reason: string }
    > {
      const rawPath = args["path"]
      const rawContent = args["content"]
      if (typeof rawPath !== "string") return { ok: false, reason: "path is required" }
      if (typeof rawContent !== "string") return { ok: false, reason: "content is required" }
      if (Buffer.byteLength(rawContent, "utf8") > MAX_WRITE_BYTES) {
        return { ok: false, reason: `content exceeds ${MAX_WRITE_BYTES} bytes` }
      }
      if (rawContent.includes("\0")) {
        return { ok: false, reason: "refusing binary content" }
      }
      const resolved = resolveUnderWorkspace(workspaceRootFrom(ctx), rawPath)
      if (!resolved.ok) return resolved

      // P2 fix 2026-09-04: capture pre-write content for /undo command.
      // null = file was new (no previous content). Push BEFORE writing.
      const beforeContent = (() => {
        try {
          return readFileSync(resolved.path, "utf8")
        } catch {
          return null
        }
      })()
      // D75 T1 (CQ-003): single-file undo + chain undo push consolidated
      // into recordWriteUndo in workspace-tools-undo.ts.
      recordWriteUndo({ ctx, resolvedPath: resolved.path, beforeContent })

      const written = await writeTextToWorkspace({
        ctx,
        resolvedPath: resolved.path,
        content: rawContent,
        toolName: "write_file",
      })
      if (!written.ok) return written
      return {
        ok: true,
        output: `wrote ${rawPath.trim()} (${rawContent.length} chars)`,
      }
    },
  }
}

/**
 * Phase 7 fix F14: `write_file` requires the model to re-emit the whole file.
 * On a 1600-line page that meant huge outputs, context overflow, and silent
 * regressions of earlier features (observed: 书籍设置 / ↑↓ lost after a
 * whole-file rewrite). `edit_file` replaces a unique snippet in place.
 */
export function makeEditFileTool(ctx: WorkspaceToolContext = {}): ToolDefinition {
  return {
    name: makeToolName("edit_file"),
    risk: "high",
    async run(
      args: Record<string, unknown>,
    ): Promise<
      | { readonly ok: true; readonly output: unknown }
      | { readonly ok: false; readonly reason: string }
    > {
      const rawPath = args["path"]
      const oldText = args["oldText"]
      const newText = args["newText"]
      const replaceAll = args["replaceAll"] === true
      if (typeof rawPath !== "string") return { ok: false, reason: "path is required" }
      if (typeof oldText !== "string" || oldText.length === 0) {
        return { ok: false, reason: "oldText is required (non-empty exact snippet)" }
      }
      if (typeof newText !== "string") return { ok: false, reason: "newText is required" }
      if (newText.includes("\0")) return { ok: false, reason: "refusing binary content" }
      const resolved = resolveUnderWorkspace(workspaceRootFrom(ctx), rawPath)
      if (!resolved.ok) return resolved

      let before: string
      try {
        const st = statSync(resolved.path)
        if (!st.isFile()) return { ok: false, reason: "path is not a file" }
        before = readFileSync(resolved.path, "utf8")
      } catch {
        return {
          ok: false,
          reason: `file not found: ${rawPath.trim()}（先用 read_file 确认路径与原文）`,
        }
      }

      const occurrences = before.split(oldText).length - 1
      if (occurrences === 0) {
        return {
          ok: false,
          reason: `oldText not found in ${rawPath.trim()}（先用 read_file 读取原文，确保片段逐字一致）`,
        }
      }
      if (occurrences > 1 && !replaceAll) {
        return {
          ok: false,
          reason: `oldText matches ${occurrences} places in ${rawPath.trim()}；请补足上下文使其唯一，或传 replaceAll:true`,
        }
      }
      const after = replaceAll
        ? before.split(oldText).join(newText)
        : (() => {
            const at = before.indexOf(oldText)
            return before.slice(0, at) + newText + before.slice(at + oldText.length)
          })()
      if (Buffer.byteLength(after, "utf8") > MAX_EDIT_RESULT_BYTES) {
        return { ok: false, reason: `edited file exceeds ${MAX_EDIT_RESULT_BYTES} bytes` }
      }

      recordWriteUndo({ ctx, resolvedPath: resolved.path, beforeContent: before })
      const written = await writeTextToWorkspace({
        ctx,
        resolvedPath: resolved.path,
        content: after,
        toolName: "edit_file",
      })
      if (!written.ok) return written
      const delta = after.length - before.length
      return {
        ok: true,
        output:
          `edited ${rawPath.trim()} (${occurrences} replacement(s), ` +
          `${before.length} -> ${after.length} chars, ${delta >= 0 ? "+" : ""}${delta})`,
      }
    },
  }
}

// D75 T1 (CQ-003): undo state + helpers moved to workspace-tools-undo.ts.
// workspace-tools.ts owns the tool definitions; the undo module owns
// the persistent in-memory undo state + chain revert logic. The split
// drops workspace-tools.ts from 811 → ~570 lines.
//
// Re-export the public undo surface here so downstream consumers
// (acceptance tests + wechat-undo-command + owner-routes/audit-fatigue)
// can keep importing from `@butler/api/workspace-tools.js`. The state
// itself lives in workspace-tools-undo.ts; this file just forwards
// the public symbols so the API surface is preserved.
export {
  popMostRecentWrite,
  recordWriteUndo,
  resetUndoChain,
  resetUndoStack,
  undoChain,
  UNDO_CHAIN_CONV_FOR_TEST,
  UNDO_CHAIN_FOR_TEST,
  undoChain_listChainIds,
  undoChain_listConversations,
  undoLastWrite,
  getUndoChainConversation,
  type ChainEntry,
  type ChainRevertResult,
} from "./workspace-tools-undo.js"

export type RunCommandArgsResult =
  | { readonly ok: true; readonly argv: readonly string[] }
  | { readonly ok: false; readonly reason: string }

/**
 * run_command 的纯参数校验（不触碰沙箱）。
 * 审批边界在批准前先用它做 preflight，避免空参数调用占用审批轮次（ISSUE-11）。
 */
export function validateRunCommandArgs(
  args: Readonly<Record<string, unknown>>,
): RunCommandArgsResult {
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
  return { ok: true, argv }
}

export function makeRunCommandTool(ctx: WorkspaceToolContext = {}): ToolDefinition {
  return {
    name: makeToolName("run_command"),
    risk: "high",
    async run(
      args: Record<string, unknown>,
      signal?: AbortSignal,
    ): Promise<
      | { readonly ok: true; readonly output: unknown }
      | { readonly ok: false; readonly reason: string; readonly exitCode?: number }
    > {
      const parsed = validateRunCommandArgs(args)
      if (!parsed.ok) return { ok: false, reason: parsed.reason }
      const argv: string[] = [...parsed.argv]
      if (signal?.aborted) {
        return { ok: false, reason: "aborted" }
      }
      const cwd = sandboxWorkspaceRootFrom(ctx)
      const { executeArgvInSandbox, createDefaultProcessRunner, resolveSandboxGitIdentityEnv } =
        await import("@butler/adapters/sandbox/bubblewrap-runner.js")
      const { currentNetworkAllowlist, currentSandboxProfileName } =
        await import("@butler/runtime/sandbox/index.js")
      const sandboxRunner = createDefaultProcessRunner()
      // P2 credential host-injection: resolve + merge allowed named credentials.
      const requestedCred = normalizeCredentialNames(args["credentials"])
      let injectedEnv: Readonly<Record<string, string>> = {}
      if (requestedCred.length > 0) {
        const provider = ctx.credentialProvider ?? createHostCredentialProvider(process.env)
        const allowlist =
          ctx.credentialAllowlist ??
          (process.env["BUTLER_V5_RUN_COMMAND_CREDENTIALS"] ?? "")
            .split(",")
            .map((s) => s.trim())
            .filter((s) => s.length > 0)
        const injected = await injectRunCommandCredentials({
          provider,
          requestedNames: requestedCred,
          allowlist,
          baseEnv: {},
        })
        if (!injected.ok) return { ok: false, reason: injected.reason }
        injectedEnv = injected.env
      }
      const started = Date.now()
      const sandboxed = await executeArgvInSandbox({
        argv,
        workspaceRoot: cwd,
        profileName: currentSandboxProfileName(),
        networkAllowlist: currentNetworkAllowlist(),
        env: process.env,
        injectEnv: injectedEnv,
        runner: sandboxRunner,
      })
      if ("mode" in sandboxed && sandboxed.mode === "disabled") {
        const result = await spawnCaptured(argv, cwd, signal, {
          ...resolveSandboxGitIdentityEnv(argv),
          ...injectedEnv,
        })
        await recordExecAudit(ctx.audit, {
          cmd: argv.join(" "),
          cwd,
          exit: result.exitCode,
          durationMs: Date.now() - started,
          outcome: result.ok ? "ok" : "failed",
          detail: { tool: "run_command" },
        })

        // D49: chain push (best-effort; capture all run_command side-effects for owner visibility)
        await pushCommandToChain(ctx, argv, cwd, started, result.exitCode)

        return result.ok
          ? { ok: true, output: result.output }
          : result.exitCode === null
            ? { ok: false, reason: result.reason }
            : { ok: false, reason: result.reason, exitCode: result.exitCode }
      }
      await recordExecAudit(ctx.audit, {
        cmd: argv.join(" "),
        cwd,
        exit: null,
        durationMs: Date.now() - started,
        outcome: sandboxed.ok ? "ok" : "failed",
        detail: { tool: "run_command" },
      })

      const sandboxedResult: SpawnCapturedResult = sandboxed.ok
        ? {
            ok: true,
            output:
              "stdout" in sandboxed ? (sandboxed.stdout ?? "") : "sandboxed run returned no output",
            exitCode: null,
          }
        : {
            ok: false,
            reason: sandboxed.reason ?? "sandbox failed",
            exitCode: sandboxed.exitCode ?? null,
          }

      // D49: chain push
      await pushCommandToChain(ctx, argv, cwd, started, sandboxedResult.exitCode)

      if (!sandboxedResult.ok) {
        // 保留命令自己的退出码：审批恢复路径据此把“测试失败”当工具结果继续对话。
        return sandboxedResult.exitCode === null
          ? { ok: false, reason: sandboxedResult.reason }
          : { ok: false, reason: sandboxedResult.reason, exitCode: sandboxedResult.exitCode }
      }
      return { ok: true, output: sandboxedResult.output }
    },
  }
}

type SpawnCapturedResult =
  | { readonly ok: true; readonly output: unknown; readonly exitCode: number | null }
  | { readonly ok: false; readonly reason: string; readonly exitCode: number | null }

/**
 * F18: 超时/中止时连同孙进程一起杀掉。
 *
 * 真实事故：子代理执行 `pnpm build` 超时，只 kill 了 pnpm 本体，
 * `sh -c next build` 与 node 构建进程变成孤儿继续写 `.next`，
 * 后续构建拿不到一致的构建目录而长时间挂起（无任何日志）。
 * POSIX 下用 detached 让子进程自成进程组，abort 时 kill(-pid) 整组回收。
 */
function killProcessTree(child: ReturnType<typeof spawn>, processGroup: boolean): void {
  const pid = child.pid
  if (processGroup && typeof pid === "number" && pid > 0) {
    try {
      process.kill(-pid, "SIGKILL")
      return
    } catch {
      // 进程组已退出或无权操作：退回只杀直接子进程。
    }
  }
  try {
    child.kill("SIGKILL")
  } catch {
    // 进程已退出，忽略。
  }
}

function spawnCaptured(
  argv: readonly string[],
  cwd: string,
  signal?: AbortSignal,
  injectedEnv: Readonly<Record<string, string>> = {},
): Promise<SpawnCapturedResult> {
  const program = argv[0]
  if (!program) return Promise.resolve({ ok: false, reason: "argv is required", exitCode: null })
  // POSIX 下开启 detached，使 child 成为新进程组组长，便于整组回收。
  const processGroup = process.platform !== "win32"
  return new Promise((resolvePromise) => {
    if (signal?.aborted) {
      resolvePromise({ ok: false, reason: "aborted", exitCode: null })
      return
    }
    let child: ReturnType<typeof spawn>
    try {
      child = spawn(program, argv.slice(1), {
        cwd,
        env: { PATH: process.env["PATH"] ?? "/usr/bin:/bin", ...injectedEnv },
        stdio: ["ignore", "pipe", "pipe"],
        detached: processGroup,
      })
    } catch (err) {
      resolvePromise({
        ok: false,
        reason: err instanceof Error ? err.message : String(err),
        exitCode: null,
      })
      return
    }
    const chunks: Buffer[] = []
    let total = 0
    const onAbort = () => {
      killProcessTree(child, processGroup)
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
      resolvePromise({ ok: false, reason: err.message, exitCode: null })
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
          exitCode: code,
        })
        return
      }
      resolvePromise({ ok: true, output: clipped, exitCode: code })
    })
  })
}

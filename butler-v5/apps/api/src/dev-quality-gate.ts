/**
 * P4: automatic dev verification after exec runs (write/command/subagent).
 */
import { spawn } from "node:child_process"
import { resolve } from "node:path"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import type { ButlerLoopResult } from "./wechat-inbound-butler.js"
import { loadQualityGateConfig } from "./wechat-quality-gate.js"
import { updateProjectState } from "./project-state.js"
import { isRunNotifyEnabled, sendWechatProactiveNotify } from "./wechat-run-notify.js"
import { recordExecAudit, type ExecAuditContext } from "./exec-audit.js"

export type DevVerifyResult = {
  readonly ok: boolean
  readonly exitCode: number
  readonly commandLabel: string
  readonly outputExcerpt: string
  readonly durationMs: number
}

export function isDevVerifyAutoEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  const raw = (env["BUTLER_V5_DEV_VERIFY_ENABLED"] ?? "1").trim().toLowerCase()
  return raw !== "0" && raw !== "false" && raw !== "off"
}

/** When true, inbound waits for verify to finish (slow). Default async + WeChat push. */
export function isDevVerifyInlineEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  const raw = (env["BUTLER_V5_DEV_VERIFY_INLINE"] ?? "0").trim().toLowerCase()
  return raw === "1" || raw === "true" || raw === "yes" || raw === "on"
}

export function workspaceRootFromEnv(env: NodeJS.ProcessEnv = process.env): string {
  return (env["BUTLER_V5_WORKSPACE_ROOT"] ?? process.cwd()).trim() || process.cwd()
}

export function resolveDevVerifyCwd(projectId: string, env: NodeJS.ProcessEnv = process.env): string {
  const root = workspaceRootFromEnv(env)
  const gateProject = loadQualityGateConfig(env)?.projects?.[projectId.trim()]
  const rel = gateProject?.cwd?.trim()
  return rel ? resolve(root, rel) : root
}

export function resolveDevVerifyArgv(env: NodeJS.ProcessEnv = process.env): readonly string[] {
  const raw = (env["BUTLER_V5_DEV_VERIFY_CMD"] ?? "").trim()
  if (raw) {
    if (raw.startsWith("[")) {
      try {
        const parsed: unknown = JSON.parse(raw)
        if (Array.isArray(parsed) && parsed.every((part) => typeof part === "string")) {
          return parsed as readonly string[]
        }
      } catch {
        // fall through
      }
    }
    return raw.split(/\s+/u).filter((part) => part.length > 0)
  }
  return ["pnpm", "test"]
}

export function devVerifyTimeoutMs(env: NodeJS.ProcessEnv = process.env): number {
  const raw = Number(env["BUTLER_V5_DEV_VERIFY_TIMEOUT_MS"] ?? 300_000)
  return Number.isFinite(raw) && raw > 0 ? Math.floor(raw) : 300_000
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text
  return `${text.slice(0, max)}…`
}

export async function runArgv(args: {
  readonly argv: readonly string[]
  readonly cwd: string
  readonly timeoutMs: number
  readonly env?: NodeJS.ProcessEnv
  readonly audit?: ExecAuditContext
}): Promise<{ readonly code: number; readonly output: string; readonly durationMs: number }> {
  const command = args.argv[0]
  if (!command) {
    return { code: 1, output: "empty argv", durationMs: 0 }
  }
  const rest = args.argv.slice(1)
  const started = Date.now()
  return new Promise((resolvePromise) => {
    const child = spawn(command, [...rest], {
      cwd: args.cwd,
      env: { ...process.env, ...args.env },
      stdio: ["ignore", "pipe", "pipe"],
    })
    let stdout = ""
    let stderr = ""
    child.stdout?.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf8")
    })
    child.stderr?.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf8")
    })
    const timer = setTimeout(() => {
      child.kill("SIGTERM")
    }, args.timeoutMs)
    const finish = async (code: number, output: string, durationMs: number) => {
      clearTimeout(timer)
      await recordExecAudit(args.audit, {
        cmd: args.argv.join(" "),
        cwd: args.cwd,
        exit: code,
        durationMs,
        outcome: code === 0 ? "ok" : "failed",
        detail: { kind: "dev-verify" },
      })
      resolvePromise({ code, output, durationMs })
    }
    child.on("close", (code) => {
      const output = truncate(`${stdout}${stderr}`.trim(), 1200)
      void finish(code ?? 1, output || "(no output)", Date.now() - started)
    })
    child.on("error", (err) => {
      void finish(1, err.message, Date.now() - started)
    })
  })
}

export async function listGitTouchedPaths(args: {
  readonly cwd: string
  readonly env?: NodeJS.ProcessEnv
  readonly limit?: number
  readonly audit?: ExecAuditContext
}): Promise<readonly string[]> {
  const limit = args.limit ?? 12
  const result = await runArgv({
    argv: ["git", "diff", "--name-only", "HEAD"],
    cwd: args.cwd,
    timeoutMs: 15_000,
    ...(args.env === undefined ? {} : { env: args.env }),
    ...(args.audit ? { audit: args.audit } : {}),
  })
  if (result.code !== 0) {
    const staged = await runArgv({
      argv: ["git", "diff", "--name-only", "--cached"],
    cwd: args.cwd,
    timeoutMs: 15_000,
    ...(args.env === undefined ? {} : { env: args.env }),
      ...(args.audit ? { audit: args.audit } : {}),
    })
    if (staged.code !== 0) return []
    return staged.output
      .split(/\r?\n/u)
      .map((line) => line.trim())
      .filter((line) => line.length > 0)
      .slice(0, limit)
  }
  const untracked = await runArgv({
    argv: ["git", "ls-files", "--others", "--exclude-standard"],
    cwd: args.cwd,
    timeoutMs: 15_000,
    ...(args.env === undefined ? {} : { env: args.env }),
    ...(args.audit ? { audit: args.audit } : {}),
  })
  const merged = new Set<string>()
  for (const line of result.output.split(/\r?\n/u)) {
    const trimmed = line.trim()
    if (trimmed) merged.add(trimmed)
  }
  if (untracked.code === 0) {
    for (const line of untracked.output.split(/\r?\n/u)) {
      const trimmed = line.trim()
      if (trimmed) merged.add(trimmed)
    }
  }
  return [...merged].slice(0, limit)
}

export async function resolveGitBranch(args: {
  readonly cwd: string
  readonly env?: NodeJS.ProcessEnv
  readonly audit?: ExecAuditContext
}): Promise<string | undefined> {
  const result = await runArgv({
    argv: ["git", "rev-parse", "--abbrev-ref", "HEAD"],
    cwd: args.cwd,
    timeoutMs: 10_000,
    ...(args.env === undefined ? {} : { env: args.env }),
    ...(args.audit ? { audit: args.audit } : {}),
  })
  if (result.code !== 0) return undefined
  const branch = result.output.trim()
  return branch.length > 0 ? branch : undefined
}

export async function runDevVerify(args: {
  readonly projectId: string
  readonly env?: NodeJS.ProcessEnv
  readonly audit?: ExecAuditContext
}): Promise<DevVerifyResult> {
  const env = args.env ?? process.env
  const argv = resolveDevVerifyArgv(env)
  const cwd = resolveDevVerifyCwd(args.projectId, env)
  const run = await runArgv({
    argv,
    cwd,
    timeoutMs: devVerifyTimeoutMs(env),
    env,
    ...(args.audit ? { audit: args.audit } : {}),
  })
  return {
    ok: run.code === 0,
    exitCode: run.code,
    commandLabel: argv.join(" "),
    outputExcerpt: run.output,
    durationMs: run.durationMs,
  }
}

function projectStateVerifyPatch(args: {
  readonly verify: DevVerifyResult
  readonly touchedPaths: readonly string[]
  readonly branch?: string
  readonly wipSummary: string
}) {
  return {
    lastTouchedPaths: [...args.touchedPaths],
    wipSummary: args.wipSummary,
    lastVerifyOk: args.verify.ok,
    lastVerifyCommand: args.verify.commandLabel,
    lastVerifyExitCode: args.verify.exitCode,
    lastVerifyAtMs: Date.now(),
    ...(args.branch ? { branch: args.branch } : {}),
  }
}

export function formatDevQualityReply(args: {
  readonly projectId: string
  readonly baseReply: string
  readonly verify: DevVerifyResult
  readonly touchedPaths: readonly string[]
}): string {
  const lines = [`【开发验收】项目 ${args.projectId}`]
  if (args.touchedPaths.length > 0) {
    lines.push("", "改动文件：")
    for (const path of args.touchedPaths) {
      lines.push(`· ${path}`)
    }
  } else {
    lines.push("", "改动文件：（未检测到 git diff）")
  }
  const mark = args.verify.ok ? "✓" : "✗"
  const seconds = (args.verify.durationMs / 1000).toFixed(1)
  lines.push(
    "",
    `测试：${mark} ${args.verify.commandLabel} (exit ${args.verify.exitCode}, ${seconds}s)`,
  )
  if (!args.verify.ok && args.verify.outputExcerpt) {
    lines.push(truncate(args.verify.outputExcerpt, 400))
  }
  const body = args.baseReply.trim()
  if (body) {
    lines.push("", "---", body)
  }
  return lines.join("\n")
}

export function loopUsedDirectExecTools(
  loop: Pick<ButlerLoopResult, "traces">,
): boolean {
  return loop.traces.some(
    (t) => t.startsWith("write_file@") || t.startsWith("run_command@"),
  )
}

export function shouldAutoDevVerify(args: {
  readonly includeExecTools: boolean
  readonly loop: Pick<ButlerLoopResult, "finalDecision" | "toolCalls" | "traces">
  readonly env?: NodeJS.ProcessEnv
}): boolean {
  const env = args.env ?? process.env
  if (!isDevVerifyAutoEnabled(env)) return false
  if (!args.includeExecTools) return false
  if (args.loop.finalDecision === "WaitForApproval") return false
  if (args.loop.toolCalls <= 0) return false
  return loopUsedDirectExecTools(args.loop)
}

function formatDevVerifyPendingReply(args: {
  readonly projectId: string
  readonly baseReply: string
  readonly commandLabel: string
  readonly touchedPaths: readonly string[]
}): string {
  const lines = [`【开发验收】项目 ${args.projectId}`]
  if (args.touchedPaths.length > 0) {
    lines.push("", "改动文件：")
    for (const path of args.touchedPaths) {
      lines.push(`· ${path}`)
    }
  } else {
    lines.push("", "改动文件：（未检测到 git diff）")
  }
  lines.push("", `测试：运行中 ${args.commandLabel}（完成后微信推送结果）`)
  const body = args.baseReply.trim()
  if (body) {
    lines.push("", "---", body)
  }
  return lines.join("\n")
}

function scheduleAsyncDevVerify(args: {
  readonly projectId: string
  readonly fromUserId: string
  readonly baseReply: string
  readonly cwd: string
  readonly env: NodeJS.ProcessEnv
  readonly runtimeStore?: RuntimeStore
}): void {
  void (async () => {
    const audit: ExecAuditContext | undefined = args.runtimeStore
      ? { runtimeStore: args.runtimeStore, subject: args.fromUserId }
      : undefined
    const [verify, touchedPaths, branch] = await Promise.all([
      runDevVerify({ projectId: args.projectId, env: args.env, ...(audit ? { audit } : {}) }),
      listGitTouchedPaths({ cwd: args.cwd, env: args.env, ...(audit ? { audit } : {}) }),
      resolveGitBranch({ cwd: args.cwd, env: args.env, ...(audit ? { audit } : {}) }),
    ])
    updateProjectState({
      userId: args.fromUserId,
      projectId: args.projectId,
      patch: projectStateVerifyPatch({
        verify,
        touchedPaths,
        branch,
        wipSummary: verify.ok ? "验收通过" : "验收失败",
      }),
      env: args.env,
    })
    if (!isRunNotifyEnabled(args.env)) return
    const to = args.fromUserId.trim()
    if (!to) return
    const text = formatDevQualityReply({
      projectId: args.projectId,
      baseReply: args.baseReply,
      verify,
      touchedPaths,
    })
    await sendWechatProactiveNotify({ to, text, env: args.env })
  })().catch(() => {
    // best-effort background verify
  })
}

export function shouldAutoDevVerifySubagent(args: {
  readonly capabilities: readonly string[]
  readonly ok: boolean
  readonly env?: NodeJS.ProcessEnv
}): boolean {
  const env = args.env ?? process.env
  if (!isDevVerifyAutoEnabled(env)) return false
  if (!args.ok) return false
  return args.capabilities.some((cap) => cap === "run_command" || cap === "write_file")
}

export async function enrichDevRunResult(args: {
  readonly projectId: string
  readonly fromUserId: string
  readonly includeExecTools: boolean
  readonly loop: ButlerLoopResult
  readonly env?: NodeJS.ProcessEnv
  readonly runtimeStore?: RuntimeStore
}): Promise<ButlerLoopResult> {
  const env = args.env ?? process.env
  if (!shouldAutoDevVerify({ includeExecTools: args.includeExecTools, loop: args.loop, env })) {
    return args.loop
  }
  const audit: ExecAuditContext | undefined = args.runtimeStore
    ? { runtimeStore: args.runtimeStore, subject: args.fromUserId }
    : undefined
  const cwd = resolveDevVerifyCwd(args.projectId, env)
  const commandLabel = resolveDevVerifyArgv(env).join(" ")
  const [touchedPaths, branch] = await Promise.all([
    listGitTouchedPaths({ cwd, env, ...(audit ? { audit } : {}) }),
    resolveGitBranch({ cwd, env, ...(audit ? { audit } : {}) }),
  ])

  if (!isDevVerifyInlineEnabled(env)) {
    scheduleAsyncDevVerify({
      projectId: args.projectId,
      fromUserId: args.fromUserId,
      baseReply: args.loop.reply,
      cwd,
      env,
      ...(args.runtimeStore ? { runtimeStore: args.runtimeStore } : {}),
    })
    updateProjectState({
      userId: args.fromUserId,
      projectId: args.projectId,
      patch: {
        lastTouchedPaths: [...touchedPaths],
        wipSummary: "验收运行中",
        ...(branch ? { branch } : {}),
      },
      env,
    })
    return {
      ...args.loop,
      reply: formatDevVerifyPendingReply({
        projectId: args.projectId,
        baseReply: args.loop.reply,
        commandLabel,
        touchedPaths,
      }),
      traces: [...args.loop.traces, "dev-verify: async-scheduled"],
    }
  }

  const [verify, freshTouchedPaths, freshBranch] = await Promise.all([
    runDevVerify({ projectId: args.projectId, env, ...(audit ? { audit } : {}) }),
    listGitTouchedPaths({ cwd, env, ...(audit ? { audit } : {}) }),
    resolveGitBranch({ cwd, env, ...(audit ? { audit } : {}) }),
  ])
  updateProjectState({
    userId: args.fromUserId,
    projectId: args.projectId,
    patch: projectStateVerifyPatch({
      verify,
      touchedPaths: freshTouchedPaths,
      branch: freshBranch,
      wipSummary: verify.ok ? "验收通过" : "验收失败",
    }),
    env,
  })
  const reply = formatDevQualityReply({
    projectId: args.projectId,
    baseReply: args.loop.reply,
    verify,
    touchedPaths: freshTouchedPaths,
  })
  return {
    ...args.loop,
    reply,
    traces: [...args.loop.traces, `dev-verify: exit=${verify.exitCode}`],
  }
}

export async function enrichSubagentDevReply(args: {
  readonly projectId: string
  readonly fromUserId: string
  readonly capabilities: readonly string[]
  readonly ok: boolean
  readonly baseReply: string
  readonly env?: NodeJS.ProcessEnv
  readonly runtimeStore?: RuntimeStore
}): Promise<string> {
  const env = args.env ?? process.env
  if (!shouldAutoDevVerifySubagent({ capabilities: args.capabilities, ok: args.ok, env })) {
    return args.baseReply
  }
  const audit: ExecAuditContext | undefined = args.runtimeStore
    ? { runtimeStore: args.runtimeStore, subject: args.fromUserId }
    : undefined
  const cwd = resolveDevVerifyCwd(args.projectId, env)
  const [verify, touchedPaths, branch] = await Promise.all([
    runDevVerify({ projectId: args.projectId, env, ...(audit ? { audit } : {}) }),
    listGitTouchedPaths({ cwd, env, ...(audit ? { audit } : {}) }),
    resolveGitBranch({ cwd, env, ...(audit ? { audit } : {}) }),
  ])
  updateProjectState({
    userId: args.fromUserId,
    projectId: args.projectId,
    patch: projectStateVerifyPatch({
      verify,
      touchedPaths,
      branch,
      wipSummary: verify.ok ? "子代理验收通过" : "子代理验收失败",
    }),
    env,
  })
  return formatDevQualityReply({
    projectId: args.projectId,
    baseReply: args.baseReply,
    verify,
    touchedPaths,
  })
}

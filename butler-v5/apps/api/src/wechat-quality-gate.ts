import { spawn } from "node:child_process"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import { getWechatActiveProjectId } from "./wechat-active-project.js"
import type { ButlerLoopResult } from "./wechat-inbound-butler.js"
import { recordExecAudit, type ExecAuditContext } from "./exec-audit.js"

export type QualityGateCommand = {
  readonly name: string
  readonly argv: readonly string[]
  readonly timeoutMs?: number
}

export type QualityGateProject = {
  readonly cwd?: string
  readonly commands: readonly QualityGateCommand[]
}

export type QualityGateConfig = {
  readonly version: number
  readonly projects?: Readonly<Record<string, QualityGateProject>>
}

function workspaceRootFromEnv(env: NodeJS.ProcessEnv): string {
  return (env["BUTLER_V5_WORKSPACE_ROOT"] ?? process.cwd()).trim() || process.cwd()
}

export function qualityGateConfigPath(env: NodeJS.ProcessEnv = process.env): string {
  const configured = (env["BUTLER_V5_QUALITY_GATE_CONFIG"] ?? "").trim()
  if (configured) return configured
  return resolve(process.cwd(), "config/quality-gate.json")
}

export function loadQualityGateConfig(env: NodeJS.ProcessEnv = process.env): QualityGateConfig | null {
  try {
    const parsed: unknown = JSON.parse(readFileSync(qualityGateConfigPath(env), "utf8"))
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null
    return parsed as QualityGateConfig
  } catch {
    return null
  }
}

function gateProject(
  inboundProjectId: string,
  env: NodeJS.ProcessEnv,
): QualityGateProject | undefined {
  return loadQualityGateConfig(env)?.projects?.[inboundProjectId.trim()]
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text
  return `${text.slice(0, max)}…`
}

async function runArgv(args: {
  readonly argv: readonly string[]
  readonly cwd: string
  readonly timeoutMs: number
  readonly env: NodeJS.ProcessEnv
  readonly audit?: ExecAuditContext
}): Promise<{ readonly code: number; readonly output: string }> {
  const command = args.argv[0]
  if (!command) {
    return { code: 1, output: "empty argv" }
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
    const finish = async (code: number, output: string) => {
      clearTimeout(timer)
      await recordExecAudit(args.audit, {
        cmd: args.argv.join(" "),
        cwd: args.cwd,
        exit: code,
        durationMs: Date.now() - started,
        outcome: code === 0 ? "ok" : "failed",
        detail: { kind: "quality-gate" },
      })
      resolvePromise({ code, output })
    }
    child.on("close", (code) => {
      const output = truncate(`${stdout}${stderr}`.trim(), 800)
      void finish(code ?? 1, output || "(no output)")
    })
    child.on("error", (err) => {
      void finish(1, err.message)
    })
  })
}

function done(reply: string, traces: readonly string[]): ButlerLoopResult {
  return {
    reply,
    iterations: 0,
    toolCalls: 0,
    finalDecision: "Respond",
    traces: [...traces],
  }
}

export async function tryWechatQualityGateCommand(args: {
  readonly fromUserId: string
  readonly content: string
  readonly env?: NodeJS.ProcessEnv
  readonly runtimeStore?: RuntimeStore
}): Promise<ButlerLoopResult | null> {
  const env = args.env ?? process.env
  const trimmed = args.content.trim()
  if (trimmed !== "/验" && trimmed !== "/门禁" && !trimmed.startsWith("/验 ")) {
    return null
  }

  const active = getWechatActiveProjectId(args.fromUserId, env)
  const project = gateProject(active, env)
  if (!project || project.commands.length === 0) {
    return done(
      `项目「${active}」未配置质量门禁。\n编辑 config/quality-gate.json 后重试。`,
      ["quality-gate: missing config"],
    )
  }

  const nameFilter =
    trimmed.startsWith("/验 ") && trimmed.length > "/验 ".length
      ? trimmed.slice("/验 ".length).trim()
      : undefined
  const commands = nameFilter
    ? project.commands.filter((cmd) => cmd.name === nameFilter)
    : project.commands
  if (commands.length === 0) {
    return done(`未找到门禁「${nameFilter}」。`, ["quality-gate: unknown name"])
  }

  const root = workspaceRootFromEnv(env)
  const cwd = resolve(root, (project.cwd ?? ".").trim() || ".")
  const lines = [`【${active} 质量门禁】`]
  let failed = 0
  const audit: ExecAuditContext | undefined = args.runtimeStore
    ? { runtimeStore: args.runtimeStore, subject: args.fromUserId }
    : undefined

  for (const cmd of commands) {
    const timeoutMs = cmd.timeoutMs ?? 60_000
    const result = await runArgv({
      argv: cmd.argv,
      cwd,
      timeoutMs,
      env,
      ...(audit ? { audit } : {}),
    })
    const mark = result.code === 0 ? "✓" : "✗"
    if (result.code !== 0) failed += 1
    lines.push(`${mark} ${cmd.name} (exit ${result.code})`)
    if (result.code !== 0 && result.output) {
      lines.push(truncate(result.output, 300))
    }
  }

  lines.push("", failed === 0 ? "全部通过。" : `${failed} 项失败。`)
  return done(lines.join("\n"), [`quality-gate: ${active} failed=${failed}`])
}

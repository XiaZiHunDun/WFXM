import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { resolveProjectKnowledgeInboundProjectId } from "@butler/domain/knowledge/project-knowledge.js"
import {
  getWechatActiveProjectId,
  parseWechatProjectCatalog,
  resolveWechatProjectAlias,
  setWechatActiveProjectId,
} from "./wechat-active-project.js"
import { normalizeWechatSwitchCommand } from "./wechat-project-switch.js"
import type { ButlerLoopResult } from "./wechat-inbound-butler.js"
import type { McpToolBundle } from "./mcp-bootstrap.js"
import type { Wiring } from "./wiring.js"
import { resolveWechatAllowedToolNames } from "./wechat-tool-allowlist.js"
import { formatProjectStateLines, getProjectState } from "./project-state.js"

export type WechatProjectPathEntry = {
  readonly label?: string
  readonly readmePath?: string
  readonly manifestPath?: string
}

export type WechatProjectPathsConfig = {
  readonly version: number
  readonly projects?: Readonly<Record<string, WechatProjectPathEntry>>
}

function workspaceRootFromEnv(env: NodeJS.ProcessEnv): string {
  return (env["BUTLER_V5_WORKSPACE_ROOT"] ?? process.cwd()).trim() || process.cwd()
}

export function wechatProjectPathsConfigPath(env: NodeJS.ProcessEnv = process.env): string {
  const configured = (env["BUTLER_V5_WECHAT_PROJECT_PATHS"] ?? "").trim()
  if (configured) return configured
  return resolve(process.cwd(), "config/wechat-project-paths.json")
}

export function loadWechatProjectPathsConfig(
  env: NodeJS.ProcessEnv = process.env,
): WechatProjectPathsConfig | null {
  try {
    const text = readFileSync(resolve(wechatProjectPathsConfigPath(env)), "utf8")
    const parsed: unknown = JSON.parse(text)
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null
    const root = parsed as Record<string, unknown>
    if (typeof root["version"] !== "number") return null
    return parsed as WechatProjectPathsConfig
  } catch {
    return null
  }
}

export function projectPathEntry(
  inboundProjectId: string,
  env: NodeJS.ProcessEnv = process.env,
): WechatProjectPathEntry | undefined {
  return loadWechatProjectPathsConfig(env)?.projects?.[inboundProjectId.trim()]
}

function readHeadLines(absPath: string, maxLines: number): string | undefined {
  try {
    const text = readFileSync(absPath, "utf8")
    return text
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line.length > 0 && !line.startsWith("#"))
      .slice(0, maxLines)
      .join("\n")
  } catch {
    return undefined
  }
}

function extractYamlDescription(manifestText: string): string | undefined {
  for (const line of manifestText.split(/\r?\n/)) {
    if (line.startsWith("description:")) {
      return line.slice("description:".length).trim()
    }
  }
  return undefined
}

export function summarizeWechatToolProfile(args: {
  readonly projectId: string
  readonly env?: NodeJS.ProcessEnv
  readonly mcpBundle?: McpToolBundle
}): { readonly total: number; readonly mcp: number; readonly label: string } {
  const env = args.env ?? process.env
  const allowed =
    resolveWechatAllowedToolNames({
      projectId: args.projectId,
      env,
      mcpBundle: args.mcpBundle,
    }) ?? []
  const mcp = allowed.filter((name) => name.startsWith("mcp_")).length
  const core = allowed.length - mcp
  const label =
    mcp === 0
      ? `${core} 核心`
      : mcp >= 20
        ? `${core} 核心 + MCP 全量(${mcp})`
        : `${core} 核心 + ${mcp} MCP`
  return { total: allowed.length, mcp, label: label }
}

async function pkCountForInbound(
  wiring: Wiring,
  inboundProjectId: string,
  env: NodeJS.ProcessEnv,
): Promise<number | null> {
  const store = wiring.projectKnowledgeStore
  if (!store) return null
  const pkProjectId = resolveProjectKnowledgeInboundProjectId(inboundProjectId, env)
  const items = await store.listByProject({ projectId: pkProjectId, limit: 500 })
  return items.length
}

async function pendingTaskCount(wiring: Wiring, subject: string): Promise<number | null> {
  const store = wiring.taskStore
  if (!store) return null
  const items = await store.listBySubject({ subject, status: "open", limit: 100 })
  return items.length
}

function doneResult(
  reply: string,
  traces: readonly string[],
  finalDecision: ButlerLoopResult["finalDecision"] = "Respond",
): ButlerLoopResult {
  return {
    reply,
    iterations: 0,
    toolCalls: 0,
    finalDecision,
    traces: [...traces],
  }
}

function formatProjectListLine(args: {
  readonly item: { readonly id: string; readonly label: string }
  readonly active: boolean
  readonly pkCount: number | null
  readonly tools: string
}): string {
  const marker = args.active ? "→ " : "  "
  const pk =
    args.pkCount === null ? "PK ?" : `PK ${args.pkCount}`
  return `${marker}${args.item.id}（${args.item.label}）· ${pk} · ${args.tools}`
}

async function buildProjectListReply(args: {
  readonly wiring: Wiring
  readonly fromUserId: string
  readonly env: NodeJS.ProcessEnv
  readonly mcpBundle?: McpToolBundle
}): Promise<string> {
  const active = getWechatActiveProjectId(args.fromUserId, args.env)
  const lines: string[] = [`项目列表（当前：${active}）`]
  for (const item of parseWechatProjectCatalog(args.env)) {
    const pkCount = await pkCountForInbound(args.wiring, item.id, args.env)
    const tools = summarizeWechatToolProfile({
      projectId: item.id,
      env: args.env,
      mcpBundle: args.mcpBundle,
    }).label
    lines.push(
      formatProjectListLine({
        item,
        active: item.id === active,
        pkCount,
        tools,
      }),
    )
  }
  lines.push("", "命令：/切换 <名> · /项目概况 · /项目 体检")
  return lines.join("\n")
}

type ProjectSurfaceArgs = {
  readonly wiring: Wiring
  readonly fromUserId: string
  readonly env: NodeJS.ProcessEnv
  readonly mcpBundle?: McpToolBundle
}

/**
 * Resolve the active project context shared by the status / overview /
 * health replies: active id + label, PK count + store id, and tool profile.
 */
async function activeProjectContext(
  args: ProjectSurfaceArgs,
): Promise<{
  readonly active: string
  readonly label: string
  readonly pkCount: number | null
  readonly pkStoreId: string
  readonly tools: ReturnType<typeof summarizeWechatToolProfile>
}> {
  const active = getWechatActiveProjectId(args.fromUserId, args.env)
  const catalog = parseWechatProjectCatalog(args.env)
  const label = catalog.find((item) => item.id === active)?.label ?? active
  const pkCount = await pkCountForInbound(args.wiring, active, args.env)
  const pkStoreId = resolveProjectKnowledgeInboundProjectId(active, args.env)
  const tools = summarizeWechatToolProfile({
    projectId: active,
    env: args.env,
    mcpBundle: args.mcpBundle,
  })
  return { active, label, pkCount, pkStoreId, tools }
}

async function buildStatusReply(args: ProjectSurfaceArgs): Promise<string> {
  const { active, label, pkCount, pkStoreId, tools } = await activeProjectContext(args)
  const openTasks = await pendingTaskCount(args.wiring, args.fromUserId)
  const devState = getProjectState({
    userId: args.fromUserId,
    projectId: active,
    env: args.env,
  })
  const stateLines = formatProjectStateLines(devState)
  const lines = [
    `当前项目：${active}（${label}）`,
    `知识库：${pkCount ?? "?"} 条（store: ${pkStoreId}）`,
    `工具：${tools.label}`,
  ]
  if (stateLines.length > 0) {
    lines.push(...stateLines)
  }
  if (openTasks !== null) {
    lines.push(`待办：${openTasks} 条 open（/待办 查看）`)
  }
  lines.push("", "发送 /项目概况 查看摘要，/项目 体检 做只读检查。")
  return lines.join("\n")
}

async function buildOverviewReply(args: ProjectSurfaceArgs): Promise<string> {
  const { active, label, pkCount, pkStoreId, tools } = await activeProjectContext(args)
  const paths = projectPathEntry(active, args.env)
  const root = workspaceRootFromEnv(args.env)
  const lines = [`【${active}（${label}）概况】`]

  if (paths?.manifestPath) {
    try {
      const manifest = readFileSync(resolve(root, paths.manifestPath), "utf8")
      const desc = extractYamlDescription(manifest)
      if (desc) lines.push(`描述：${desc}`)
    } catch {
      lines.push(`描述：（未读到 ${paths.manifestPath}）`)
    }
  }

  if (paths?.readmePath) {
    const head = readHeadLines(resolve(root, paths.readmePath), 2)
    if (head) lines.push("", head)
  }

  lines.push(
    "",
    `知识库 ${pkCount ?? "?"} 条（${pkStoreId}）· 工具 ${tools.label}`,
  )
  const openTasks = await pendingTaskCount(args.wiring, args.fromUserId)
  if (openTasks !== null) {
    lines.push(`待办 ${openTasks} 条 open（/待办）`)
  }
  return lines.join("\n")
}

async function buildHealthReply(args: {
  readonly fromUserId: string
  readonly env: NodeJS.ProcessEnv
  readonly mcpBundle?: McpToolBundle
}): Promise<string> {
  const active = getWechatActiveProjectId(args.fromUserId, args.env)
  const paths = projectPathEntry(active, args.env)
  const root = workspaceRootFromEnv(args.env)
  const checks: string[] = [`【${active} 体检】`]

  if (!paths) {
    checks.push("⚠ 未配置 wechat-project-paths.json 条目（仅检查 PK/工具）")
  } else {
    for (const [name, rel] of [
      ["readme", paths.readmePath],
      ["manifest", paths.manifestPath],
    ] as const) {
      if (!rel) continue
      const abs = resolve(root, rel)
      try {
        readFileSync(abs)
        checks.push(`✓ ${name}: ${rel}`)
      } catch {
        checks.push(`✗ ${name} 缺失: ${rel}`)
      }
    }
  }

  const tools = summarizeWechatToolProfile({
    projectId: active,
    env: args.env,
    mcpBundle: args.mcpBundle,
  })
  checks.push(`✓ 工具配置：${tools.label}`)
  checks.push("", "（只读检查；执行测试请用 /验）")
  return checks.join("\n")
}

function switchReply(
  projectId: string,
  env: NodeJS.ProcessEnv,
  mcpBundle?: McpToolBundle,
): ButlerLoopResult {
  const catalog = parseWechatProjectCatalog(env)
  const label = catalog.find((item) => item.id === projectId)?.label ?? projectId
  const pkStoreId = resolveProjectKnowledgeInboundProjectId(projectId, env)
  const tools = summarizeWechatToolProfile({ projectId, env, mcpBundle })
  return doneResult(
    [
      `已切换到项目：${projectId}（${label}）`,
      `知识库：${pkStoreId} · 工具：${tools.label}`,
      "后续消息使用新会话。发送 /项目概况 或 /状态 查看详情。",
    ].join("\n"),
    [`project-switch: ${projectId}`],
  )
}

/**
 * WeChat project commands: switch, list, status, overview, health.
 * Returns null when the message is not a project command.
 */
export async function tryWechatProjectCommand(args: {
  readonly wiring: Wiring
  readonly fromUserId: string
  readonly content: string
  readonly env?: NodeJS.ProcessEnv
  readonly mcpBundle?: McpToolBundle
}): Promise<ButlerLoopResult | null> {
  const env = args.env ?? process.env
  const resolvedArgs = { ...args, env }
  const trimmed = args.content.trim()
  const normalized = normalizeWechatSwitchCommand(trimmed) ?? trimmed

  if (normalized === "/项目" || normalized === "/switch list" || normalized === "/projects") {
    return doneResult(
      await buildProjectListReply(resolvedArgs),
      ["project-surface: list"],
    )
  }

  if (
    normalized === "/状态" ||
    normalized === "/status" ||
    normalized === "当前在哪个项目" ||
    normalized === "当前项目是什么"
  ) {
    return doneResult(await buildStatusReply(resolvedArgs), ["project-surface: status"])
  }

  if (
    normalized === "/项目概况" ||
    normalized === "/概况" ||
    normalized === "/project overview"
  ) {
    return doneResult(await buildOverviewReply(resolvedArgs), ["project-surface: overview"])
  }

  if (normalized === "/项目 体检" || normalized === "/体检") {
    return doneResult(await buildHealthReply(resolvedArgs), ["project-surface: health"])
  }

  if (normalized.startsWith("/切换") || normalized.startsWith("/switch")) {
    const sep = normalized.startsWith("/切换") ? "/切换" : "/switch"
    const name = normalized.slice(sep.length).trim()
    if (!name) {
      return doneResult(
        `用法：/切换 <项目名>\n\n${await buildProjectListReply(resolvedArgs)}`,
        ["project-switch: missing name"],
      )
    }
    const projectId = resolveWechatProjectAlias(name, env)
    if (!projectId) {
      return doneResult(
        `未知项目「${name}」。\n\n${await buildProjectListReply(resolvedArgs)}`,
        [`project-switch: unknown ${name}`],
        "Finish",
      )
    }
    setWechatActiveProjectId(args.fromUserId, projectId, env)
    return switchReply(projectId, env, args.mcpBundle)
  }

  return null
}

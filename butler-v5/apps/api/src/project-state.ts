/**
 * Per-user per-project dev state (JSON file MVP — no migration required).
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { homedir } from "node:os"
import { dirname, join } from "node:path"

export type ChildRunStatus = "queued" | "running" | "succeeded" | "failed"

export type ProjectStateRecord = {
  readonly branch?: string
  readonly wipSummary?: string
  readonly lastTouchedPaths?: readonly string[]
  readonly lastDevRunId?: string
  readonly lastChildRunId?: string
  readonly lastChildRunStatus?: ChildRunStatus
  readonly lastChildRunRole?: string
  readonly lastChildRunTask?: string
  readonly lastVerifyOk?: boolean
  readonly lastVerifyCommand?: string
  readonly lastVerifyExitCode?: number
  readonly lastVerifyAtMs?: number
  readonly updatedAtMs?: number
}

type ProjectStateStore = Record<string, ProjectStateRecord>

const DEFAULT_STORE_PATH = join(homedir(), ".config", "butler-v5", "project-state.json")

export function projectStateStorePath(env: NodeJS.ProcessEnv = process.env): string {
  const configured = (env["BUTLER_V5_PROJECT_STATE_STORE"] ?? "").trim()
  return configured || DEFAULT_STORE_PATH
}

function stateKey(userId: string, projectId: string): string {
  return `${userId.trim()}::${projectId.trim()}`
}

function readStore(path: string): ProjectStateStore {
  try {
    const raw = readFileSync(path, "utf8")
    const parsed: unknown = JSON.parse(raw)
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      return {}
    }
    return parsed as ProjectStateStore
  } catch {
    return {}
  }
}

function writeStore(path: string, store: ProjectStateStore): void {
  mkdirSync(dirname(path), { recursive: true })
  writeFileSync(path, `${JSON.stringify(store, null, 2)}\n`, "utf8")
}

export function getProjectState(args: {
  readonly userId: string
  readonly projectId: string
  readonly env?: NodeJS.ProcessEnv
}): ProjectStateRecord | null {
  const env = args.env ?? process.env
  const store = readStore(projectStateStorePath(env))
  return store[stateKey(args.userId, args.projectId)] ?? null
}

export function updateProjectState(args: {
  readonly userId: string
  readonly projectId: string
  readonly patch: Partial<ProjectStateRecord>
  readonly env?: NodeJS.ProcessEnv
}): ProjectStateRecord {
  const env = args.env ?? process.env
  const path = projectStateStorePath(env)
  const store = readStore(path)
  const key = stateKey(args.userId, args.projectId)
  const prev = store[key] ?? {}
  const next: ProjectStateRecord = {
    ...prev,
    ...args.patch,
    updatedAtMs: Date.now(),
  }
  store[key] = next
  writeStore(path, store)
  return next
}

export function childRunStatusLabel(status: ChildRunStatus | undefined): string {
  switch (status) {
    case "queued":
      return "排队中"
    case "running":
      return "执行中"
    case "succeeded":
      return "已完成"
    case "failed":
      return "失败"
    default:
      return "未知"
  }
}

export function recordChildRunDelegated(args: {
  readonly userId: string
  readonly projectId: string
  readonly childRunId: string | null
  readonly role: string
  readonly task: string
  readonly env?: NodeJS.ProcessEnv
}): ProjectStateRecord {
  return updateProjectState({
    userId: args.userId,
    projectId: args.projectId,
    patch: {
      ...(args.childRunId ? { lastChildRunId: args.childRunId } : {}),
      lastChildRunStatus: "queued",
      lastChildRunRole: args.role.trim().slice(0, 40) || "developer",
      lastChildRunTask: args.task.trim().slice(0, 120),
    },
    ...(args.env === undefined ? {} : { env: args.env }),
  })
}

export function recordChildRunStatus(args: {
  readonly userId: string
  readonly projectId: string
  readonly childRunId: string
  readonly status: ChildRunStatus
  readonly env?: NodeJS.ProcessEnv
}): ProjectStateRecord | null {
  const current = getProjectState(args)
  if (current?.lastChildRunId && current.lastChildRunId !== args.childRunId) {
    return null
  }
  return updateProjectState({
    userId: args.userId,
    projectId: args.projectId,
    patch: {
      lastChildRunId: args.childRunId,
      lastChildRunStatus: args.status,
    },
    ...(args.env === undefined ? {} : { env: args.env }),
  })
}

export function formatProjectStateLines(state: ProjectStateRecord | null): readonly string[] {
  if (!state) return []
  const lines: string[] = []
  if (state.branch) lines.push(`分支：${state.branch}`)
  if (state.wipSummary) lines.push(`进行中：${state.wipSummary}`)
  if (state.lastTouchedPaths && state.lastTouchedPaths.length > 0) {
    const shown = state.lastTouchedPaths.slice(0, 5).join(", ")
    lines.push(`最近改动：${shown}`)
  }
  if (state.lastChildRunId || state.lastChildRunStatus) {
    const role = state.lastChildRunRole ?? "developer"
    const status = childRunStatusLabel(state.lastChildRunStatus)
    const id = state.lastChildRunId ? `${state.lastChildRunId.slice(0, 8)}…` : "—"
    lines.push(`子代理：${role} · ${status} · ${id}`)
    if (state.lastChildRunTask) {
      lines.push(`子代理任务：${state.lastChildRunTask}`)
    }
  }
  if (state.lastDevRunId) lines.push(`末次开发 Run：${state.lastDevRunId.slice(0, 8)}…`)
  if (state.lastVerifyAtMs) {
    const mark = state.lastVerifyOk ? "✓" : "✗"
    const cmd = state.lastVerifyCommand ?? "verify"
    const exitCode = state.lastVerifyExitCode ?? "?"
    lines.push(`末次验收：${mark} ${cmd} (exit ${exitCode})`)
  }
  return lines
}

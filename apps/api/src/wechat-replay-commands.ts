/**
 * Phase 6 P1: owner-facing replay queue.
 *
 * `/复盘 [n]` lists the most recent failed turns from persisted traces, and
 * `/转用例 <turnId>` turns one of them into a skipped acceptance-scenario
 * draft. This is the "在线失败 → 回归用例" link of the loop; without it the
 * analysis stage ends at a number nobody can act on.
 */
import { mkdir, writeFile } from "node:fs/promises"
import { join, resolve } from "node:path"
import type { TraceEvent } from "@butler/domain/observability/local-trace.js"
import { isFailedRunTrace } from "@butler/domain/observability/local-trace.js"
import { turnIdShort } from "@butler/domain/observability/error-codes.js"
import {
  buildScenarioDraft,
  renderDraftTest,
  slugify,
} from "@butler/domain/observability/scenario-draft.js"
import { getSharedLocalTracer } from "@butler/runtime/observability/local-tracer.js"
import { isWechatObservabilityOwner } from "./wechat-observability-commands.js"
import type { ButlerLoopResult } from "./wechat-inbound-butler.js"
import type { Wiring } from "./wiring.js"

const DAY_MS = 24 * 60 * 60 * 1000
const REPLAY_WINDOW_MS = 7 * DAY_MS
export const DEFAULT_REPLAY_LIMIT = 5
export const MAX_REPLAY_LIMIT = 20
export const DEFAULT_DRAFT_DIR = "tests/acceptance/scenarios/drafts"

export type WechatReplayCommand =
  | { readonly kind: "list"; readonly limit: number }
  | { readonly kind: "to_scenario"; readonly token: string }

export function parseWechatReplayCommand(content: string): WechatReplayCommand | null {
  const trimmed = content.trim()
  const listMatch = /^\/复盘(?:\s+(\S+))?$/.exec(trimmed)
  if (listMatch) {
    const raw = listMatch[1]
    const parsed = raw === undefined ? DEFAULT_REPLAY_LIMIT : Number.parseInt(raw, 10)
    const limit =
      Number.isFinite(parsed) && parsed > 0
        ? Math.min(parsed, MAX_REPLAY_LIMIT)
        : DEFAULT_REPLAY_LIMIT
    return { kind: "list", limit }
  }
  const scenarioMatch = /^\/转用例(?:\s+(\S+))?$/.exec(trimmed)
  if (scenarioMatch) {
    const token = scenarioMatch[1]?.trim()
    return token ? { kind: "to_scenario", token } : { kind: "to_scenario", token: "" }
  }
  return null
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

function workspaceRootFromEnv(env: Readonly<Record<string, string | undefined>>): string {
  return (env["BUTLER_V5_WORKSPACE_ROOT"] ?? process.cwd()).trim() || process.cwd()
}

export function resolveDraftDir(env: Readonly<Record<string, string | undefined>>): string {
  const explicit = (env["BUTLER_V5_EVAL_DRAFT_DIR"] ?? DEFAULT_DRAFT_DIR).trim()
  return resolve(workspaceRootFromEnv(env), explicit)
}

function shanghaiHourMinute(ms: number): string {
  const d = new Date(ms + 8 * 60 * 60 * 1000)
  const pad = (n: number) => n.toString().padStart(2, "0")
  return `${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(
    d.getUTCMinutes(),
  )}`
}

function detailString(event: TraceEvent, key: string): string | null {
  const value = event.detail[key]
  return typeof value === "string" && value.length > 0 ? value : null
}

async function readWindowEvents(args: {
  readonly wiring: Wiring
  readonly env: Readonly<Record<string, string | undefined>>
  readonly nowMs: number
}): Promise<{
  readonly events: readonly TraceEvent[]
  readonly source: "store" | "memory" | "none"
}> {
  const sinceMs = args.nowMs - REPLAY_WINDOW_MS
  if (args.wiring.traceStore) {
    const rows = await args.wiring.traceStore
      .list({ sinceMs, untilMs: args.nowMs, limit: 5000 })
      .catch(() => null)
    if (rows !== null) return { events: rows, source: "store" }
  }
  const tracer = getSharedLocalTracer(args.env)
  if (!tracer.config.enabled) return { events: [], source: "none" }
  return {
    events: tracer
      .list({ limit: 5000 })
      .filter((event) => event.createdAt >= sinceMs && event.createdAt <= args.nowMs),
    source: "memory",
  }
}

interface FailedTurn {
  readonly turnId: string
  readonly event: TraceEvent
  /** Tool seen anywhere in the turn — terminal events often omit it. */
  readonly tool: string | null
}

function toolOf(event: TraceEvent): string | null {
  const tool = detailString(event, "tool")
  if (tool) return tool
  // `detail.name` is only a tool name on step events; on run events it can
  // be a lifecycle label ("finish") that would read as a tool.
  return event.kind === "step" ? detailString(event, "name") : null
}

function turnKey(event: TraceEvent): string {
  return event.turnId ?? `run:${event.runId ?? event.id}`
}

/** Latest failure event per turn, newest first. */
export function groupFailedTurns(events: readonly TraceEvent[]): readonly FailedTurn[] {
  const failed = new Map<string, TraceEvent>()
  for (const event of events) {
    if (!isFailedRunTrace(event)) continue
    const key = turnKey(event)
    const prev = failed.get(key)
    if (!prev || event.createdAt > prev.createdAt) failed.set(key, event)
  }

  // Terminal events usually drop the tool; pick it up from any event that
  // belongs to the same failed turn.
  const tools = new Map<string, string>()
  for (const event of events) {
    const key = turnKey(event)
    if (!failed.has(key) || tools.has(key)) continue
    const tool = toolOf(event)
    if (tool) tools.set(key, tool)
  }

  return [...failed.entries()]
    .map(([turnId, event]) => ({ turnId, event, tool: tools.get(turnId) ?? null }))
    .sort((a, b) => b.event.createdAt - a.event.createdAt)
}

export function formatReplayList(
  turns: readonly FailedTurn[],
  source: "store" | "memory" | "none",
): string {
  if (source === "none") return "轨迹功能未启用（BUTLER_V5_TRACE=0），看不到失败记录。"
  if (turns.length === 0) return "近 7 天没有失败记录。"
  const lines = [`最近失败 turn（${turns.length} 个）：`]
  for (const turn of turns) {
    const parts = [
      shanghaiHourMinute(turn.event.createdAt),
      `[${turnIdShort(turn.turnId) || turn.turnId}]`,
    ]
    const code = detailString(turn.event, "code")
    if (code) parts.push(code)
    if (turn.tool) parts.push(`· ${turn.tool}`)
    lines.push(`· ${parts.join(" ")}`)
  }
  lines.push("回复「/转用例 <turnId>」生成回归草稿。")
  return lines.join("\n")
}

async function loadTurnEvents(args: {
  readonly wiring: Wiring
  readonly env: Readonly<Record<string, string | undefined>>
  readonly token: string
  readonly nowMs: number
}): Promise<readonly TraceEvent[]> {
  const store = args.wiring.traceStore
  if (store) {
    const exact = await store.list({ turnId: args.token, limit: 5000 }).catch(() => null)
    if (exact && exact.length > 0) return exact
  }
  const { events } = await readWindowEvents({
    wiring: args.wiring,
    env: args.env,
    nowMs: args.nowMs,
  })
  const matchedTurnId = events.find(
    (event) =>
      typeof event.turnId === "string" &&
      event.turnId.length > 0 &&
      (event.turnId === args.token || event.turnId.startsWith(args.token)),
  )?.turnId
  if (!matchedTurnId) return []
  return events.filter((event) => event.turnId === matchedTurnId)
}

export async function tryWechatReplayCommand(args: {
  readonly wiring: Wiring
  readonly fromUserId: string
  readonly content: string
  readonly env?: NodeJS.ProcessEnv
  readonly nowMs?: () => number
}): Promise<ButlerLoopResult | null> {
  const command = parseWechatReplayCommand(args.content)
  if (!command) return null
  const env = args.env ?? process.env
  if (!isWechatObservabilityOwner(args.fromUserId, env)) return null
  const nowMs = args.nowMs?.() ?? Date.now()

  if (command.kind === "list") {
    const { events, source } = await readWindowEvents({ wiring: args.wiring, env, nowMs })
    const turns = groupFailedTurns(events).slice(0, command.limit)
    return done(formatReplayList(turns, source), [`wechat-replay: ${source} ${turns.length}`])
  }

  if (!command.token) {
    return done("用法：/转用例 <turnId>（先用 /复盘 查看最近失败）", [
      "wechat-replay: to-scenario usage",
    ])
  }
  const events = await loadTurnEvents({
    wiring: args.wiring,
    env,
    token: command.token,
    nowMs,
  })
  if (events.length === 0) {
    return done(`未找到 turn ${command.token} 的轨迹，请先用 /复盘 确认 turnId。`, [
      "wechat-replay: turn not found",
    ])
  }

  const turnId = events.find((event) => event.turnId)?.turnId ?? command.token
  const draft = buildScenarioDraft(events, { turnId })
  const dir = resolveDraftDir(env)
  const slug = slugify(turnId)
  const jsonPath = join(dir, `${slug}.json`)
  const testPath = join(dir, `${slug}.draft.test.ts`)
  try {
    await mkdir(dir, { recursive: true })
    await writeFile(jsonPath, `${JSON.stringify(draft, null, 2)}\n`, "utf8")
    await writeFile(testPath, renderDraftTest(draft), "utf8")
  } catch (err) {
    const reason = err instanceof Error ? err.message : String(err)
    return done(`生成草稿失败：${reason}`, ["wechat-replay: write failed"])
  }

  return done(
    [
      `已生成回归草稿（${events.length} 条轨迹）：`,
      `· ${jsonPath}`,
      `· ${testPath}`,
      "请人工补齐期望后移入正式场景目录。",
    ].join("\n"),
    [`wechat-replay: to-scenario ${turnId}`],
  )
}

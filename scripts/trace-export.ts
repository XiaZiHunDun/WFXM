#!/usr/bin/env node
/* eslint-disable no-console -- CLI entrypoint: stdout carries JSONL, stderr carries summaries */
/**
 * `pnpm trace:export` — export persisted trace events as JSONL.
 *
 * Reads the same database the API writes to (`BUTLER_V5_DB` / `DATABASE_URL`
 * / `BUTLER_V5_PGLITE_DIR`), so an operator can pull a failure window and
 * attach it to a bug report without exposing server logs.
 *
 * Usage:
 *   pnpm trace:export
 *   pnpm trace:export --since 2026-11-20 --until 2026-11-25
 *   pnpm trace:export --kind step --turn turn-172 --limit 500
 *   pnpm trace:export --conversation c-wechat-owner --out traces.jsonl
 */
import { createWriteStream } from "node:fs"
import { once } from "node:events"
import { fileURLToPath } from "node:url"
import type { TraceKind } from "@butler/domain/observability/local-trace.js"
import {
  createTraceStore,
  openButlerDatabase,
  type TraceListFilter,
  type TraceStore,
} from "@butler/persistence"

const TRACE_KINDS: readonly TraceKind[] = [
  "run",
  "step",
  "capability",
  "policy",
  "grant",
  "approval",
]

const DEFAULT_LIMIT = 1000

export const TRACE_EXPORT_HELP = `trace:export — 导出 trace_events 为 JSONL

用法：pnpm trace:export [选项]

选项：
  --since <时间>         起始时间（含）。YYYY-MM-DD 按 Asia/Shanghai 当日 00:00 起算
  --until <时间>         结束时间（含）。YYYY-MM-DD 按当日 23:59:59.999 起算
  --kind <kind>          run | step | capability | policy | grant | approval
  --turn <turnId>        按 turnId 精确过滤
  --conversation <id>    按 conversationId 精确过滤
  --limit <n>            最多导出条数（默认 ${DEFAULT_LIMIT}）
  --out <文件>           写入文件；缺省写 stdout
  -h, --help             显示本帮助

数据库连接沿用 API 的环境变量（BUTLER_V5_DB / DATABASE_URL / BUTLER_V5_PGLITE_DIR）。
`

export interface TraceExportOptions {
  readonly filter: TraceListFilter
  readonly out?: string
}

function requireValue(argv: readonly string[], index: number, flag: string): string {
  const value = argv[index]
  if (value === undefined || value.startsWith("--")) {
    throw new Error(`${flag} 缺少取值`)
  }
  return value
}

function parseBoundary(raw: string, endOfDay: boolean): number {
  const text = raw.trim()
  const dayOnly = /^\d{4}-\d{2}-\d{2}$/.test(text)
  const suffix = endOfDay ? "23:59:59.999" : "00:00:00.000"
  const ms = dayOnly ? Date.parse(`${text}T${suffix}+08:00`) : Date.parse(text)
  if (!Number.isFinite(ms)) throw new Error(`无法解析时间：${raw}`)
  return ms
}

function parseLimit(raw: string): number {
  const value = Number.parseInt(raw, 10)
  if (!Number.isFinite(value) || value <= 0) throw new Error(`--limit 需为正整数：${raw}`)
  return value
}

function parseKind(raw: string): TraceKind {
  const value = raw.trim()
  if (!TRACE_KINDS.includes(value as TraceKind)) {
    throw new Error(`未知 kind：${raw}（可选：${TRACE_KINDS.join(" / ")}）`)
  }
  return value as TraceKind
}

export function parseTraceExportArgs(
  argv: readonly string[],
): TraceExportOptions | { readonly help: true } {
  let sinceMs: number | undefined
  let untilMs: number | undefined
  let kind: TraceKind | undefined
  let turnId: string | undefined
  let conversationId: string | undefined
  let limit = DEFAULT_LIMIT
  let out: string | undefined

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i]
    switch (arg) {
      case undefined:
        break
      case "-h":
      case "--help":
        return { help: true }
      case "--since":
        sinceMs = parseBoundary(requireValue(argv, i + 1, "--since"), false)
        i += 1
        break
      case "--until":
        untilMs = parseBoundary(requireValue(argv, i + 1, "--until"), true)
        i += 1
        break
      case "--kind":
        kind = parseKind(requireValue(argv, i + 1, "--kind"))
        i += 1
        break
      case "--turn":
        turnId = requireValue(argv, i + 1, "--turn")
        i += 1
        break
      case "--conversation":
        conversationId = requireValue(argv, i + 1, "--conversation")
        i += 1
        break
      case "--limit":
        limit = parseLimit(requireValue(argv, i + 1, "--limit"))
        i += 1
        break
      case "--out":
        out = requireValue(argv, i + 1, "--out")
        i += 1
        break
      default:
        throw new Error(`未知参数：${arg}`)
    }
  }

  if (sinceMs !== undefined && untilMs !== undefined && sinceMs > untilMs) {
    throw new Error("--since 不能晚于 --until")
  }

  return {
    filter: {
      limit,
      ...(sinceMs !== undefined ? { sinceMs } : {}),
      ...(untilMs !== undefined ? { untilMs } : {}),
      ...(kind !== undefined ? { kind } : {}),
      ...(turnId !== undefined ? { turnId } : {}),
      ...(conversationId !== undefined ? { conversationId } : {}),
    },
    ...(out !== undefined ? { out } : {}),
  }
}

/** Stream matching trace events as JSONL through `write`. Returns the row count. */
export async function writeTraceJsonl(
  store: TraceStore,
  filter: TraceListFilter,
  write: (chunk: string) => void,
): Promise<number> {
  const events = await store.list(filter)
  for (const event of events) {
    write(`${JSON.stringify(event)}\n`)
  }
  return events.length
}

async function main(): Promise<void> {
  const parsed = parseTraceExportArgs(process.argv.slice(2))
  if ("help" in parsed) {
    console.log(TRACE_EXPORT_HELP)
    return
  }

  const opened = await openButlerDatabase(process.env)
  if (!opened.ok) {
    console.error(`trace:export 打开数据库失败：${opened.reason}`)
    process.exitCode = 1
    return
  }

  try {
    const store = createTraceStore(opened.value.db)
    if (parsed.out !== undefined) {
      const stream = createWriteStream(parsed.out, { encoding: "utf8" })
      let writeError: Error | null = null
      stream.on("error", (err) => {
        writeError = err
      })
      const closed = once(stream, "close")
      const count = await writeTraceJsonl(store, parsed.filter, (chunk) => {
        stream.write(chunk)
      })
      stream.end()
      await closed
      if (writeError !== null) throw writeError
      console.error(`已导出 ${count} 条到 ${parsed.out}`)
      return
    }
    const count = await writeTraceJsonl(store, parsed.filter, (chunk) => {
      process.stdout.write(chunk)
    })
    console.error(`已导出 ${count} 条到 stdout`)
  } finally {
    await opened.value.close()
  }
}

const invokedDirectly =
  process.argv[1] !== undefined && fileURLToPath(import.meta.url) === process.argv[1]

if (invokedDirectly) {
  main().catch((err: unknown) => {
    console.error(`trace:export 失败：${err instanceof Error ? err.message : String(err)}`)
    process.exitCode = 1
  })
}

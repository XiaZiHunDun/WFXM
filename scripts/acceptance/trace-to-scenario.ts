#!/usr/bin/env node
/* eslint-disable no-console -- CLI entrypoint: stdout carries summaries, stderr carries errors */
/**
 * `pnpm trace:to-scenario` — turn a persisted failure turn into an acceptance
 * scenario draft.
 *
 * Phase 6 (loop closing): today an online failure only exists as trace rows.
 * Getting it into the regression suite is manual archaeology. This CLI reads
 * one turn's persisted events and writes a *draft* (JSON + skipped test
 * skeleton) under `tests/acceptance/scenarios/drafts/`.
 *
 * It deliberately does NOT:
 *   - write into the real scenario directory,
 *   - generate assertions,
 *   - modify existing scenarios.
 * A human must fill in the input + expected outcome, then move the file.
 *
 * Usage:
 *   pnpm trace:to-scenario --turn turn-172
 *   pnpm trace:to-scenario --turn turn-172 --out /tmp/drafts
 */
import { mkdir, writeFile } from "node:fs/promises"
import { join, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { createTraceStore, openButlerDatabase } from "@butler/persistence"
import {
  buildScenarioDraft,
  renderDraftTest,
  slugify,
  type ScenarioDraft,
} from "@butler/domain/observability/scenario-draft.js"

export { buildScenarioDraft, renderDraftTest, slugify }
export type { ScenarioDraft }

export const DEFAULT_DRAFT_DIR = "tests/acceptance/scenarios/drafts"

export const TRACE_TO_SCENARIO_HELP = `trace:to-scenario — 把线上失败 turn 转成 acceptance 场景草稿

用法：pnpm trace:to-scenario --turn <turnId> [选项]

选项：
  --turn <turnId>        必填。要转成场景的 turnId（可用 /日志 或 /v1/owner/traces 查到）
  --out <目录>           草稿输出目录（默认 ${DEFAULT_DRAFT_DIR}）
  --name <slug>          文件名前缀（默认由 turnId 推导）
  -h, --help             显示本帮助

产出：
  <out>/<slug>.json            该 turn 的全部 trace 事件 + 观察到的结果
  <out>/<slug>.draft.test.ts   describe.skip 的测试骨架，需人工补齐再移入正式目录

数据库连接沿用 API 的环境变量（BUTLER_V5_DB / DATABASE_URL / BUTLER_V5_PGLITE_DIR）。
`

export interface TraceToScenarioOptions {
  readonly turnId: string
  readonly outDir: string
  readonly slug: string
}

function requireValue(argv: readonly string[], index: number, flag: string): string {
  const value = argv[index]
  if (value === undefined || value.startsWith("--")) {
    throw new Error(`${flag} 缺少取值`)
  }
  return value
}

export function parseTraceToScenarioArgs(
  argv: readonly string[],
): TraceToScenarioOptions | { readonly help: true } {
  let turnId: string | undefined
  let outDir = DEFAULT_DRAFT_DIR
  let name: string | undefined

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i]
    switch (arg) {
      case undefined:
        break
      case "-h":
      case "--help":
        return { help: true }
      case "--turn":
        turnId = requireValue(argv, i + 1, "--turn")
        i += 1
        break
      case "--out":
        outDir = requireValue(argv, i + 1, "--out")
        i += 1
        break
      case "--name":
        name = requireValue(argv, i + 1, "--name")
        i += 1
        break
      default:
        throw new Error(`未知参数：${arg}`)
    }
  }

  if (turnId === undefined || turnId.trim().length === 0) {
    throw new Error("缺少 --turn <turnId>（可用 /日志 或 /v1/owner/traces 查询）")
  }

  return {
    turnId: turnId.trim(),
    outDir,
    slug: slugify(name ?? turnId),
  }
}

async function main(): Promise<void> {
  const parsed = parseTraceToScenarioArgs(process.argv.slice(2))
  if ("help" in parsed) {
    console.log(TRACE_TO_SCENARIO_HELP)
    return
  }

  const opened = await openButlerDatabase(process.env)
  if (!opened.ok) {
    console.error(`trace:to-scenario 打开数据库失败：${opened.reason}`)
    process.exitCode = 1
    return
  }

  try {
    const store = createTraceStore(opened.value.db)
    const events = await store.list({ turnId: parsed.turnId, limit: 5000 })
    if (events.length === 0) {
      console.error(
        `未找到 turn ${parsed.turnId} 的 trace。请先在 /日志 或 /v1/owner/traces 确认 turnId。`,
      )
      process.exitCode = 1
      return
    }

    const draft = buildScenarioDraft(events, { turnId: parsed.turnId })
    const outDir = resolve(process.cwd(), parsed.outDir)
    await mkdir(outDir, { recursive: true })
    const jsonPath = join(outDir, `${parsed.slug}.json`)
    const testPath = join(outDir, `${parsed.slug}.draft.test.ts`)
    await writeFile(jsonPath, `${JSON.stringify(draft, null, 2)}\n`, "utf8")
    await writeFile(testPath, renderDraftTest(draft), "utf8")
    console.error(`已生成草稿：${jsonPath}`)
    console.error(`已生成骨架：${testPath}（默认 skip，需人工补齐）`)
    console.error(`共 ${events.length} 条事件；状态=${draft.observed.runStatus ?? "unknown"}`)
  } finally {
    await opened.value.close()
  }
}

const invokedDirectly =
  process.argv[1] !== undefined && fileURLToPath(import.meta.url) === process.argv[1]

if (invokedDirectly) {
  main().catch((err: unknown) => {
    console.error(`trace:to-scenario 失败：${err instanceof Error ? err.message : String(err)}`)
    process.exitCode = 1
  })
}

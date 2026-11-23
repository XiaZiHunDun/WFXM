#!/usr/bin/env node
/* eslint-disable no-console -- CLI entrypoint: stdout is the product interface */
/**
 * `pnpm chat` — Butler v5 对话调试入口（零微信、默认零 LLM）。
 *
 * 复用 acceptance harness（makeAcceptanceApp）：本进程内启动生产 wiring +
 * 内存 PGlite + Hono 路由，然后通过 HTTP 驱动 Butler Runtime 入口
 * `/v1/wechat/butler/inbound`。无需扫码、无需真实微信、无需 API Key。
 *
 * 用法：
 *   pnpm chat                                  # 交互 REPL（fixture LLM）
 *   pnpm chat --real                           # 用环境里的真实模型
 *   pnpm chat --legacy                         # 改走旧 /v1/wechat/inbound
 *   pnpm chat --script scripts/chat-scenario.example.json
 *   pnpm chat --dir scripts/chat-scenarios      # 批量场景
 *
 * REPL 内部命令：
 *   /help                显示帮助
 *   /reset               开始新会话
 *   /approve [taskId]    通过审批（缺省用上一轮 taskId）
 *   /reject [taskId]     拒绝审批
 *   /quit                退出
 *
 * 其余输入（含 /status、/tasks、/new、/project、/remember、/help 规则命令）
 * 原样发送给管家。
 */
import { readdirSync, readFileSync } from "node:fs"
import { join } from "node:path"
import { createInterface, type Interface as RLInterface } from "node:readline"
import { makeAcceptanceApp, type AcceptanceApp } from "../tests/acceptance/harness.js"

const INBOUND_SECRET = "test-inbound-secret-9c2f"
const BUTLER_PATH = "/v1/wechat/butler/inbound"
const LEGACY_PATH = "/v1/wechat/inbound"
const DEFAULT_PROJECT_ID = "wechat"
const DEFAULT_FROM_USER = "u-owner"

interface CliOptions {
  readonly real: boolean
  readonly legacy: boolean
  readonly verbose: boolean
  readonly workspace?: string
  readonly scriptPaths: readonly string[]
  readonly projectId: string
  readonly conversationId: string
}

interface TurnMeta {
  readonly reply: string
  readonly route?: string
  readonly rule?: string
  readonly taskId?: string
  readonly traces?: readonly string[]
}

interface ScenarioExpectation {
  readonly route?: string
  readonly rule?: string
  readonly taskId?: string
  readonly mustContain?: readonly string[]
  readonly mustNotContain?: readonly string[]
}

interface ScenarioTurn {
  readonly content?: string
  readonly waitMs?: number
  readonly approval?: { readonly taskId?: string; readonly approved: boolean }
  readonly expect?: ScenarioExpectation
}

interface Scenario {
  readonly conversationId?: string
  readonly fromUserId?: string
  readonly projectId?: string
  readonly turns: readonly ScenarioTurn[]
}

function parseArgs(argv: readonly string[]): CliOptions {
  const options: {
    real: boolean
    legacy: boolean
    verbose: boolean
    workspace?: string
    scriptPaths: string[]
    projectId: string
    conversationId: string
  } = {
    real: false,
    legacy: false,
    verbose: false,
    scriptPaths: [],
    projectId: DEFAULT_PROJECT_ID,
    conversationId: `chat-${Date.now().toString(36)}`,
  }

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index]
    if (arg === "--real") options.real = true
    else if (arg === "--legacy") options.legacy = true
    else if (arg === "--verbose") options.verbose = true
    else if (arg === "--workspace") {
      const value = argv[index + 1]
      if (!value) throw new Error("--workspace requires a path")
      options.workspace = value
      index += 1
    } else if (arg === "--script") {
      const value = argv[index + 1]
      if (!value) throw new Error("--script requires a file path")
      options.scriptPaths.push(value)
      index += 1
    } else if (arg === "--dir") {
      const value = argv[index + 1]
      if (!value) throw new Error("--dir requires a directory")
      options.scriptPaths.push(
        ...readdirSync(value)
          .filter((name) => name.endsWith(".json"))
          .sort()
          .map((name) => join(value, name)),
      )
      index += 1
    } else if (arg === "--project") {
      const value = argv[index + 1]
      if (!value) throw new Error("--project requires a project id")
      options.projectId = value
      index += 1
    } else if (arg === "--conversation") {
      const value = argv[index + 1]
      if (!value) throw new Error("--conversation requires an id")
      options.conversationId = value
      index += 1
    } else if (arg === "--help" || arg === "-h") {
      printHelp()
      process.exit(0)
    } else {
      throw new Error(`unknown argument: ${arg}`)
    }
  }
  return options
}

function printHelp(): void {
  console.log(`
Butler v5 chat (zero-WeChat debug entry)
========================================
默认：fixture LLM + 内存 PGlite + /v1/wechat/butler/inbound。

命令：
  pnpm chat                       交互 REPL
  pnpm chat --real                使用环境里的真实模型
  pnpm chat --verbose             打印每轮完整回复
  pnpm chat --workspace <path>    任务工作区（--real 默认当前仓库）

注意：--real 会真实读写所选工作区；不希望在仓库内产生副作用时，
用 --workspace 指向临时目录。
  pnpm chat --legacy              走旧 /v1/wechat/inbound
  pnpm chat --script <file.json>  跑多轮场景并断言
  pnpm chat --dir <dir>           批量跑目录下所有 *.json 场景
  pnpm chat --project <id>        指定项目（默认 wechat）

REPL 快捷命令：
  /help  /reset  /approve [taskId]  /reject [taskId]  /quit
`)
}

async function main(): Promise<void> {
  const options = parseArgs(process.argv.slice(2))
  if (!options.real) {
    // 装配期会构造 pi task layer；fixture 模式给占位值，避免误联网。
    process.env["MINIMAX_BASE_URL"] ??= "http://127.0.0.1:9/v1"
    process.env["MINIMAX_API_KEY"] ??= "fixture-key"
  }
  const app = await makeAcceptanceApp({ ...(options.real ? { noFixture: true } : {}) })
  // 让任务层能解析项目根；--real 默认指向当前仓库，fixture 用临时工作区。
  const workspace = options.workspace ?? (options.real ? process.cwd() : app.workspaceRoot)
  process.env["BUTLER_V5_PROJECT_ROOTS"] = JSON.stringify({
    wechat: workspace,
    wfxm: workspace,
  })
  if (options.real || options.workspace !== undefined) {
    // 任务工具默认读取/命令 cwd；显式工作区时一并钉住。
    process.env["BUTLER_V5_WORKSPACE_ROOT"] = workspace
    process.env["BUTLER_V5_SANDBOX_WORKSPACE_ROOT"] = workspace
  }
  if (!options.real) app.setFixtures(defaultFixtures())

  try {
    if (options.scriptPaths.length > 0) {
      let failures = 0
      for (const path of options.scriptPaths) {
        console.log(`\n# ${path}`)
        failures += await runScenario(app, options, path)
      }
      if (failures > 0) process.exitCode = 1
    } else {
      await runRepl(app, options)
    }
  } finally {
    await app.close()
  }
}

function defaultFixtures() {
  const replies = Array.from({ length: 50 }, (_, index) => ({
    content: `（fixture 回复 #${index + 1}）脚本化 LLM 应答；用 --real 接真实模型。`,
    toolCalls: [] as never[],
    stopReason: "end_turn" as const,
  }))
  return { plan: replies, exec: replies, intake: replies }
}

async function runRepl(app: AcceptanceApp, options: CliOptions): Promise<void> {
  let conversationId = options.conversationId
  let lastTaskId: string | undefined

  const rl: RLInterface = createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: false,
  })

  console.log(`chat · ${options.legacy ? "legacy" : "butler"} · project=${options.projectId}`)
  console.log(`conversationId=${conversationId}（/help 查看命令）`)

  const inflight: { current: Promise<void> } = { current: Promise.resolve() }

  await new Promise<void>((resolve) => {
    let done = false
    const shutdown = async (): Promise<void> => {
      if (done) return
      done = true
      await inflight.current
      rl.close()
      resolve()
    }
    process.on("SIGINT", () => void shutdown())
    process.on("SIGTERM", () => void shutdown())
    rl.on("close", () => void shutdown())

    const processLine = async (raw: string): Promise<void> => {
      const input = raw.trim()
      if (!input) return
      if (input === "/help") {
        printHelp()
        return
      }
      if (input === "/quit" || input === "/exit") {
        void shutdown()
        return
      }
      if (input === "/reset") {
        conversationId = `${options.conversationId}-${Date.now().toString(36)}`
        lastTaskId = undefined
        console.log(`--- new conversation: ${conversationId} ---`)
        return
      }
      if (input.startsWith("/approve") || input.startsWith("/reject")) {
        const approved = input.startsWith("/approve")
        const taskId = input.split(/\s+/)[1] ?? lastTaskId
        if (!taskId) {
          console.log("! 还没有可审批的任务；先触发审批，或 /approve <taskId>")
          return
        }
        await sendAndPrint(app, options, conversationId, { approved, taskId }, (meta) => {
          if (meta.taskId) lastTaskId = meta.taskId
        })
        return
      }

      await sendAndPrint(app, options, conversationId, { content: input }, (meta) => {
        if (meta.taskId) lastTaskId = meta.taskId
      })
    }

    rl.on("line", (raw: string) => {
      inflight.current = inflight.current
        .then(() => processLine(raw))
        .catch((error: unknown) => {
          console.error(`! error: ${(error as Error).message}`)
        })
    })
  })
}

async function sendAndPrint(
  app: AcceptanceApp,
  options: CliOptions,
  conversationId: string,
  turn: { content: string } | { approved: boolean; taskId: string },
  onMeta: (meta: TurnMeta) => void,
): Promise<void> {
  try {
    const meta = await sendTurn(app, options, conversationId, turn)
    onMeta(meta)
    console.log(`< ${meta.reply}`)
    console.log(`  ${metaLine(meta)}`)
  } catch (error) {
    console.error(`! error: ${(error as Error).message}`)
  }
}

async function runScenario(app: AcceptanceApp, options: CliOptions, path: string): Promise<number> {
  const scenario = JSON.parse(readFileSync(path, "utf8")) as Scenario
  const conversationId = scenario.conversationId ?? options.conversationId
  const projectId = scenario.projectId ?? options.projectId
  const fromUserId = scenario.fromUserId ?? DEFAULT_FROM_USER
  let failures = 0
  let lastTaskId: string | undefined

  for (const [index, turn] of scenario.turns.entries()) {
    const label = `turn ${index + 1}`
    if (turn.waitMs !== undefined) {
      console.log(`WAIT ${label} · ${turn.waitMs}ms`)
      await new Promise((resolve) => setTimeout(resolve, turn.waitMs))
      continue
    }
    let meta: TurnMeta
    try {
      const approvalTaskId = turn.approval?.taskId ?? lastTaskId
      if (turn.approval && !approvalTaskId) {
        throw new Error("approval turn needs a taskId (or a previous task turn)")
      }
      meta = await sendTurn(
        app,
        { ...options, projectId },
        conversationId,
        turn.approval
          ? { approved: turn.approval.approved, taskId: approvalTaskId as string }
          : { content: (turn.content ?? "").replaceAll("{{taskId}}", lastTaskId ?? "") },
        fromUserId,
      )
      if (meta.taskId) lastTaskId = meta.taskId
    } catch (error) {
      failures += 1
      console.log(`FAIL ${label}: ${(error as Error).message}`)
      continue
    }
    const problems = checkExpectations(meta, turn.expect)
    if (problems.length > 0) {
      failures += 1
      console.log(`FAIL ${label}: ${problems.join("; ")}`)
      console.log(`  reply: ${meta.reply}`)
      continue
    }
    console.log(`PASS ${label} · ${metaLine(meta)}`)
    if (options.verbose) console.log(`  reply: ${meta.reply}`)
  }

  if (failures > 0) {
    console.log(`\n${failures}/${scenario.turns.length} turns failed`)
  } else {
    console.log(`all ${scenario.turns.length} turns passed`)
  }
  return failures
}

function checkExpectations(meta: TurnMeta, expect?: ScenarioExpectation): string[] {
  if (!expect) return []
  const problems: string[] = []
  if (expect.route !== undefined && meta.route !== expect.route) {
    problems.push(`route=${meta.route ?? "?"} want ${expect.route}`)
  }
  if (expect.rule !== undefined && meta.rule !== expect.rule) {
    problems.push(`rule=${meta.rule ?? "?"} want ${expect.rule}`)
  }
  if (expect.taskId !== undefined && meta.taskId !== expect.taskId) {
    problems.push(`taskId=${meta.taskId ?? "?"} want ${expect.taskId}`)
  }
  for (const text of expect.mustContain ?? []) {
    if (!meta.reply.includes(text)) problems.push(`reply missing ${JSON.stringify(text)}`)
  }
  for (const text of expect.mustNotContain ?? []) {
    if (meta.reply.includes(text)) problems.push(`reply should not contain ${JSON.stringify(text)}`)
  }
  return problems
}

function metaLine(meta: TurnMeta): string {
  const parts = [`route=${meta.route ?? "?"}`]
  if (meta.rule !== undefined) parts.push(`rule=${meta.rule}`)
  if (meta.taskId !== undefined) parts.push(`taskId=${meta.taskId}`)
  if (meta.traces !== undefined && meta.traces.length > 0) {
    parts.push(`traces=${meta.traces.join(",")}`)
  }
  return `[${parts.join(" ")}]`
}

async function sendTurn(
  app: AcceptanceApp,
  options: CliOptions,
  conversationId: string,
  turn: { content: string } | { approved: boolean; taskId: string },
  fromUserId = DEFAULT_FROM_USER,
): Promise<TurnMeta> {
  const approval = "approved" in turn
  if (approval && options.legacy) {
    throw new Error("--legacy 不支持按钮审批；请在旧入口用「确认 / 拒绝」文本")
  }

  const res = await app.request(options.legacy ? LEGACY_PATH : BUTLER_PATH, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-inbound-secret": process.env["BUTLER_V5_INBOUND_SHARED_SECRET"] ?? INBOUND_SECRET,
    },
    body: JSON.stringify(
      approval
        ? {
            apiVersion: "v1",
            fromUserId,
            messageId: messageId(),
            conversationId,
            projectId: options.projectId,
            approvalPayload: `${turn.approved ? "approve" : "reject"}:${turn.taskId}`,
          }
        : {
            apiVersion: "v1",
            fromUserId,
            content: turn.content,
            messageId: messageId(),
            conversationId,
            projectId: options.projectId,
          },
    ),
  })

  const text = await res.text()
  if (!res.ok) throw new Error(`${res.status}: ${text}`)

  let parsed: {
    readonly reply?: string
    readonly route?: string
    readonly rule?: string
    readonly taskId?: string
    readonly traces?: readonly string[]
    readonly meta?: { readonly finalDecision?: string }
  }
  try {
    parsed = JSON.parse(text) as typeof parsed
  } catch {
    return { reply: text }
  }
  return {
    reply: parsed.reply ?? "",
    ...(parsed.route === undefined ? {} : { route: parsed.route }),
    ...(parsed.rule === undefined ? {} : { rule: parsed.rule }),
    ...(parsed.taskId === undefined ? {} : { taskId: parsed.taskId }),
    ...(parsed.traces === undefined ? {} : { traces: parsed.traces }),
  }
}

function messageId(): string {
  return `m-chat-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

main().catch((error: unknown) => {
  console.error("chat failed:", error)
  process.exit(1)
})

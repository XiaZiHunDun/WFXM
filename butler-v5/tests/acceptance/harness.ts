/**
 * 微信消息模拟验收 harness — 确定性、免人工、进 CI。
 *
 * 说明（重要）：本 harness 用**脚本化 LLM fixture** 注入生产 wiring，驱动
 * 真实 `/v1/wechat/inbound` 路径（routes.ts → runButlerLoop → loop → 审批 →
 * 回发）做验收断言。**不调真模型、不开真微信、不起活服务**，全部在本进程内完成，
 * 多次运行结果一致。
 *
 * 实现基于生产已内置的 fixture 缝：设 `BUTLER_V5_LLM_FIXTURE_DIR` 后，
 * `pickLLMForRole` 会通过 `makeFixtureLLMAdapter` 读取 `<dir>/<role>.json`
 * （plan/exec/intake）按序回放预设 LLM 应答，从而让真实 HTTP 路由走脚本化 LLM。
 *
 * wiring 装配镜像 production bootstrap-wiring（PGlite、完整 stores、MCP off），
 * 额外暴露 `db`（drizzle 句柄）与 `workspaceRoot`，供用例断言 run 状态 / 审计 /
 * 审批产物。无生产代码改动。
 */
import { mkdtempSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { resetFixtureLLMCounters } from "@butler/adapters"
import { EventBridge } from "@butler/persistence/event-bridge.js"
import {
  openButlerDatabase,
  createRuntimeStore,
  createDurableMemoryStore,
  createDocumentStore,
  createProjectKnowledgeStore,
  createProcedureStore,
  createTaskStore,
  backfillRuntimeFromEventStore,
  type ButlerDb,
} from "@butler/persistence"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { systemClock } from "@butler/ports/core/clock.js"
import { makeWiring, type Wiring } from "../../apps/api/src/wiring.js"
import { bootstrapMcpTools } from "../../apps/api/src/mcp-bootstrap.js"
import { buildHonoApp } from "../../apps/api/src/acceptance-app.js"

/** 与 llm-fixture.ts 的 FixtureEntry 对齐（复制最小 shape，避免跨包类型依赖）。 */
export interface FixtureEntry {
  readonly content?: string
  readonly toolCalls?: readonly {
    readonly id: string
    readonly name: string
    readonly args: Record<string, unknown>
  }[]
  readonly stopReason?: "end_turn" | "tool_use" | "stop" | "max_tokens"
}

export interface InboundResult {
  readonly status: number
  readonly conversationId?: string
  readonly reply?: string
  readonly finalDecision?: string
  readonly toolCalls?: number
  readonly text: string
}

export interface AcceptanceApp {
  readonly request: (path: string, init: RequestInit) => Promise<Response>
  readonly wiring: Wiring
  readonly db: ButlerDb
  readonly workspaceRoot: string
  readonly fixtureDir: string
  /** 写 role json + 复位 LLM 调用计数。每次用例开始前调用。 */
  readonly setFixtures: (fixtures: {
    readonly plan?: readonly FixtureEntry[]
    readonly exec?: readonly FixtureEntry[]
    readonly intake?: readonly FixtureEntry[]
  }) => void
  readonly close: () => Promise<void>
}

const FIXTURE_DEFS: readonly { readonly role: string; readonly key: "plan" | "exec" | "intake" }[] = [
  { role: "plan", key: "plan" },
  { role: "exec", key: "exec" },
  { role: "intake", key: "intake" },
]

/**
 * 构造生产 wiring + 全新 Hono 路由，走脚本化 LLM fixture。
 *
 * 设置 `process.env.BUTLER_V5_LLM_FIXTURE_DIR` 与 `BUTLER_V5_WORKSPACE_ROOT`
 * （HTTP 路由内以 `process.env` 选择 LLM 与解析工作区根）。调用方须在
 * `afterAll` 调 `app.close()`。
 */
export async function makeAcceptanceApp(opts?: {
  readonly overrides?: Readonly<Record<string, string>>
  /**
   * 可选：传入 PGlite data dir 路径（必须已存在），使新 harness 复用同一
   * 数据库。仅 audit-state 跨重启用例需要；不传则 mkdtempSync 新建一个。
   */
  readonly pgliteDataDir?: string
}): Promise<AcceptanceApp> {
  const fixtureDir = mkdtempSync(join(tmpdir(), "wb-accept-fixture-"))
  const workspaceRoot = mkdtempSync(join(tmpdir(), "wb-accept-ws-"))
  process.env["BUTLER_V5_LLM_FIXTURE_DIR"] = fixtureDir
  process.env["BUTLER_V5_WORKSPACE_ROOT"] = workspaceRoot
  // 路由以 process.env 判 isWechatIntakeEnabled（默认 1 → routeWechatIntake）。
  // 统一关掉，走 runButlerLoop 真实回退路径（含完整微信工具集 + 审批链路）。
  process.env["BUTLER_V5_INTAKE_ENABLED"] = "0"

  const env: NodeJS.ProcessEnv = {
    BUTLER_V5_DB: "pglite",
    VITEST: "true",
    NODE_ENV: "test",
    BUTLER_V5_LLM_FIXTURE_DIR: fixtureDir,
    BUTLER_V5_WORKSPACE_ROOT: workspaceRoot,
    BUTLER_V5_MCP_ENABLED: "0",
    // HTTP 路由默认走 wechat-intake 分类路径；关闭以统一走 runButlerLoop
    // （真实回退路径，含完整微信工具集 write_file + 审批链路）。
    BUTLER_V5_INTAKE_ENABLED: "0",
    ...(opts?.overrides ?? {}),
    ...(opts?.pgliteDataDir ? { BUTLER_V5_PGLITE_DATA_DIR: opts.pgliteDataDir } : {}),
  }
  // openButlerDatabase → resolvePgliteDataDir 在 VITEST=true 或 NODE_ENV=test
  // 下强制返回 in-memory（design：tests 不污染磁盘）。跨"重启"用例需要文件
  // 持久化，向 openButlerDatabase 显式传去掉测试标记的 dbEnv，其它 env 字段
  // 保持不变。
  const dbEnv: NodeJS.ProcessEnv = opts?.pgliteDataDir
    ? (() => {
        const copy: NodeJS.ProcessEnv = { ...env }
        delete copy["VITEST"]
        delete copy["NODE_ENV"]
        return copy
      })()
    : env

  const opened = await openButlerDatabase(dbEnv)
  if (!opened.ok) {
    throw new Error(`openButlerDatabase failed: ${opened.reason}`)
  }
  const db = opened.value.db
  const workerId = "wb-accept"
  const bridge = new EventBridge({ db, workerId })
  const runtimeStore = createRuntimeStore(db)
  const durableMemoryStore = createDurableMemoryStore(db)
  const documentStore = createDocumentStore(db)
  const projectKnowledgeStore = createProjectKnowledgeStore(db)
  const procedureStore = createProcedureStore(db)
  const taskStore = createTaskStore(db)
  const runEngine = new RunEngine(runtimeStore, undefined, systemClock)
  const mcp = await bootstrapMcpTools(env, { runtimeStore })
  const wiring = makeWiring({
    bridge,
    workerId,
    runtimeStore,
    runEngine,
    db,
    mcp,
    durableMemoryStore,
    documentStore,
    projectKnowledgeStore,
    procedureStore,
    taskStore,
    channels: new Map(),
    backfillConversation: async (conversationId) => {
      await backfillRuntimeFromEventStore(db, [conversationId])
    },
  })

  const server = buildHonoApp(wiring)
  const request = server.request
  const setFixtures: AcceptanceApp["setFixtures"] = (fixtures) => {
    resetFixtureLLMCounters()
    for (const def of FIXTURE_DEFS) {
      const entries = fixtures[def.key] ?? []
      writeFileSync(
        join(fixtureDir, `${def.role}.json`),
        JSON.stringify({ responses: entries }),
        "utf8",
      )
    }
  }
  const close = async (): Promise<void> => {
    await mcp.close?.()
    await opened.value.close()
    delete process.env["BUTLER_V5_LLM_FIXTURE_DIR"]
    delete process.env["BUTLER_V5_WORKSPACE_ROOT"]
    rmSync(fixtureDir, { recursive: true, force: true })
    rmSync(workspaceRoot, { recursive: true, force: true })
  }

  return { request, wiring, db, workspaceRoot, fixtureDir, setFixtures, close }
}

let msgSeq = 0

/** POST /v1/wechat/inbound，返回状态 + 解析后的字段（含非 2xx 原文）。 */
export async function sendWechatMessage(
  app: AcceptanceApp,
  msg: { readonly content: string; readonly conversationId?: string },
): Promise<InboundResult> {
  msgSeq += 1
  const res = await app.request("/v1/wechat/inbound", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      apiVersion: "v1",
      fromUserId: "u-owner",
      content: msg.content,
      messageId: `m-${Date.now()}-${msgSeq}`,
      ...(msg.conversationId ? { conversationId: msg.conversationId } : {}),
      projectId: "wechat",
    }),
  })
  const text = await res.text()
  let parsed: {
    conversationId?: string
    meta?: { finalDecision?: string; toolCalls?: number }
    reply?: string
  } | undefined
  try {
    parsed = JSON.parse(text) as typeof parsed
  } catch {
    parsed = undefined
  }
  return {
    status: res.status,
    conversationId: parsed?.conversationId,
    reply: parsed?.reply,
    finalDecision: parsed?.meta?.finalDecision,
    toolCalls: parsed?.meta?.toolCalls,
    text,
  }
}

/** 原生 tool_call 应答（policy 会对其做 side-effect 审批门控）。 */
export function toolCallEntry(
  name: string,
  args: Record<string, unknown>,
  id = "tc-1",
): FixtureEntry {
  return { content: "", toolCalls: [{ id, name, args }], stopReason: "tool_use" }
}

/** JSON-decision 应答（runButlerLoopBody 会借 decodeDecision 解析）。 */
export function decisionEntry(decision: Record<string, unknown>): FixtureEntry {
  return {
    content: JSON.stringify(decision),
    toolCalls: [],
    stopReason: "end_turn",
  }
}

/** 纯文本答复应答。 */
export function textEntry(content: string): FixtureEntry {
  return { content, toolCalls: [], stopReason: "end_turn" }
}
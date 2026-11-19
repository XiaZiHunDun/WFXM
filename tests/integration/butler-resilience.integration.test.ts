// Anchor: inbound state/edge cases → butler loop → observable reply + DB observability.
// Covers redelivery idempotency, approval wait/deny recovery entry, empty/oversize input,
// and degraded LLM responses. Asserts user-visible text and terminal rows, never internals.
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { existsSync, mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { eq } from "drizzle-orm"
import { Effect } from "effect"
import type {
  LLMAdapter,
  LLMAssistantResponse,
  LLMMessage,
} from "../../packages/adapters/src/llm-provider.js"
import { EventBridge } from "../../packages/persistence/src/event-bridge.js"
import { createRuntimeStore } from "../../packages/persistence/src/runtime-store.js"
import { runs } from "../../packages/persistence/src/schema.js"
import { makeTestDb } from "../../packages/persistence/src/testing.js"
import { RunEngine } from "../../packages/runtime/src/run-engine.js"
import { makeWiring, type Wiring } from "../../apps/api/src/wiring.js"
import { runButlerLoop, type ButlerLoopLogger } from "../../apps/api/src/wechat-inbound-butler.js"

type TestDb = Awaited<ReturnType<typeof makeTestDb>>
type AdapterStep = (messages: readonly LLMMessage[]) => LLMAssistantResponse

const OWNER = "owner-integration"
const silentLogger: ButlerLoopLogger = { warn: () => undefined, error: () => undefined }

const ISOLATED_ENV_KEYS = [
  "BUTLER_V5_WORKSPACE_ROOT",
  "BUTLER_V5_SANDBOX",
  "BUTLER_V5_SANDBOX_WORKSPACE_ROOT",
  "BUTLER_V5_LOOP_ENGINE",
  "BUTLER_V5_KILL_SWITCH",
  "BUTLER_V5_POST_APPROVAL_LOOP",
  "BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH",
  "BUTLER_OWNER_WECHAT_ID",
  "BUTLER_V5_READ_MODEL",
  "BUTLER_V5_STUCK_LOOP_THRESHOLD",
  "BUTLER_V5_MAX_DECODE_RETRIES",
  "BUTLER_V5_MAX_EMPTY_CONTENT_RETRIES",
] as const

function textResponse(content: string): LLMAssistantResponse {
  return { content, toolCalls: [], stopReason: "end_turn" }
}

function emptyResponse(): LLMAssistantResponse {
  return { content: "", toolCalls: [], stopReason: "stop" }
}

function toolCallResponse(
  toolCalls: readonly {
    readonly id: string
    readonly name: string
    readonly args: Record<string, unknown>
  }[],
): LLMAssistantResponse {
  return { content: "", toolCalls, stopReason: "tool_use" }
}

function makeScriptedAdapter(steps: readonly AdapterStep[]): LLMAdapter {
  let index = 0
  return {
    complete: (messages) => {
      const step = steps[index] ?? (() => textResponse(""))
      index += 1
      return Effect.succeed(step(messages))
    },
  }
}

describe("butler resilience and state (integration)", () => {
  let db: TestDb
  let wiring: Wiring
  let workspace: string
  const savedEnv: Record<string, string | undefined> = {}

  beforeEach(async () => {
    for (const key of ISOLATED_ENV_KEYS) {
      savedEnv[key] = process.env[key]
      delete process.env[key]
    }
    workspace = mkdtempSync(join(tmpdir(), "butler-resilience-"))
    process.env["BUTLER_V5_WORKSPACE_ROOT"] = workspace
    db = await makeTestDb()
    const runtimeStore = createRuntimeStore(db.db)
    wiring = makeWiring({
      bridge: new EventBridge({ db: db.db, workerId: "w-integration" }),
      workerId: "w-integration",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      backfillConversation: async () => undefined,
    })
  })

  afterEach(async () => {
    for (const key of ISOLATED_ENV_KEYS) {
      const value = savedEnv[key]
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
    rmSync(workspace, { recursive: true, force: true })
    await db.close()
  })

  interface TurnOptions {
    readonly conversationId: string
    readonly content: string
    readonly adapter?: LLMAdapter
    readonly allowedToolNames?: readonly string[]
    readonly idempotencyKey?: string
  }

  async function runTurn(options: TurnOptions) {
    return runButlerLoop({
      wiring,
      conversationId: options.conversationId,
      content: options.content,
      fromUserId: OWNER,
      projectId: "p-integration",
      env: {},
      logger: silentLogger,
      ...(options.adapter ? { adapter: options.adapter } : {}),
      ...(options.allowedToolNames ? { allowedToolNames: options.allowedToolNames } : {}),
      ...(options.idempotencyKey ? { idempotencyKey: options.idempotencyKey } : {}),
    })
  }

  async function runsFor(conversationId: string) {
    return db.db.select().from(runs).where(eq(runs.conversationId, conversationId))
  }

  it("重复 messageId：第二次重放既有回复，不新增 Run、不重复 user 消息", async () => {
    const conversationId = "int-duplicate"
    const idempotencyKey = "msg-dup-1"
    const adapter = makeScriptedAdapter([() => textResponse("这条只处理一次。")])

    const first = await runTurn({ conversationId, content: "重复投递", idempotencyKey, adapter })
    expect(first.reply).toContain("只处理一次")

    const second = await runTurn({ conversationId, content: "重复投递", idempotencyKey, adapter })
    expect(second.reply).toBe(first.reply)

    const rows = await runsFor(conversationId)
    expect(rows).toHaveLength(1)
    expect(rows[0]?.status).toBe("succeeded")
    const messages = await wiring.runtimeStore.listMessages(conversationId)
    expect(messages.filter((m) => m.role === "user")).toHaveLength(1)
  })

  it("审批等待态落库 + 拒绝：Run failed，重复确认不产生新 Run", async () => {
    const conversationId = "int-approval-deny"
    const adapter = makeScriptedAdapter([
      () =>
        toolCallResponse([
          { id: "tc-write", name: "write_file", args: { path: "note.txt", content: "x" } },
        ]),
    ])

    const paused = await runTurn({
      conversationId,
      content: "写一个文件",
      allowedToolNames: ["write_file"],
      adapter,
    })
    expect(paused.reply).toContain("审批")

    const pending =
      await wiring.runtimeStore.listWaitingApprovalStepsForConversation(conversationId)
    expect(pending).toHaveLength(1)
    const runId = pending[0]?.runId
    const waitingRows = await runsFor(conversationId)
    expect(waitingRows[0]?.status).toBe("waiting_approval")

    const denied = await runTurn({
      conversationId,
      content: "拒绝",
      allowedToolNames: ["write_file"],
      adapter,
    })
    expect(denied.reply).toContain("已拒绝")
    expect(
      await wiring.runtimeStore.listWaitingApprovalStepsForConversation(conversationId),
    ).toHaveLength(0)
    expect(existsSync(join(workspace, "note.txt"))).toBe(false)

    const rows = await runsFor(conversationId)
    expect(rows).toHaveLength(1)
    expect(rows[0]?.runId).toBe(runId)
    expect(rows[0]?.status).toBe("failed")

    const lateConfirm = await runTurn({
      conversationId,
      content: "确认",
      allowedToolNames: ["write_file"],
      adapter,
    })
    expect(lateConfirm.reply).toContain("没有待审批")
    expect((await runsFor(conversationId))[0]?.status).toBe("failed")
  })

  it("空内容：不崩溃，Run succeeded，assistant 消息可回放", async () => {
    const conversationId = "int-empty"
    const result = await runTurn({
      conversationId,
      content: "",
      adapter: makeScriptedAdapter([() => textResponse("请告诉我想做什么。")]),
    })

    expect(result.reply).toContain("想做")
    const rows = await runsFor(conversationId)
    expect(rows).toHaveLength(1)
    expect(rows[0]?.status).toBe("succeeded")
    const messages = await wiring.runtimeStore.listMessages(conversationId)
    expect(messages.some((m) => m.role === "assistant")).toBe(true)
  })

  it("超长内容：spam 守卫直接返回可读提示，不崩溃也不创建 Run", async () => {
    // Current source semantics: detectSpam() short-circuits before executeInbound,
    // so there is no Run row. Asserted explicitly so future changes surface here.
    const conversationId = "int-too-long"
    // Distinct CJK chars keep the repeated-character heuristics quiet; only the
    // length guard (> 2000 chars) should fire.
    const content = Array.from({ length: 2_100 }, (_, i) =>
      String.fromCharCode(0x4e00 + (i % 700)),
    ).join("")
    const result = await runTurn({ conversationId, content })

    expect(result.reply).toContain("消息过长")
    expect(await wiring.runtimeStore.findActiveMainRun(conversationId)).toBeNull()
    expect(await runsFor(conversationId)).toHaveLength(0)
  })

  it("LLM 空响应：重试后给出可用回复，Run succeeded", async () => {
    const conversationId = "int-empty-llm"
    const adapter = makeScriptedAdapter([
      () => emptyResponse(),
      () => textResponse("兜底回答在这里。"),
    ])

    const result = await runTurn({ conversationId, content: "回答一下", adapter })
    expect(result.reply).toContain("兜底回答")
    const rows = await runsFor(conversationId)
    expect(rows[0]?.status).toBe("succeeded")
  })

  it("非法 toolCall：用户看到兜底说明，Run succeeded", async () => {
    const conversationId = "int-bad-tool"
    const adapter = makeScriptedAdapter([
      () =>
        toolCallResponse([{ id: "tc-bad", name: "definitely_not_a_registered_tool", args: {} }]),
      () => textResponse("那个工具不可用，我改用文字回答。"),
    ])

    const result = await runTurn({ conversationId, content: "用那个工具", adapter })
    expect(result.reply).toContain("改用文字")
    const rows = await runsFor(conversationId)
    expect(rows[0]?.status).toBe("succeeded")
  })
})

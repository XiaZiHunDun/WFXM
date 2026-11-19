// Anchor: one inbound owner turn → butler loop → LLM/tool boundary → DB terminal Run
// + assistant message + workspace artifact. Outcome-only: reply fragments, Run status,
// message roles, file bytes. No private fields, prompt text, tool ordering or call counts.
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { basename, join } from "node:path"
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

/**
 * workspace-tools reads BUTLER_V5_WORKSPACE_ROOT from process.env directly (not
 * from the runButlerLoop env arg), so isolate the process env for these cases.
 */
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

function toolCallResponse(
  toolCalls: readonly {
    readonly id: string
    readonly name: string
    readonly args: Record<string, unknown>
  }[],
): LLMAssistantResponse {
  return { content: "", toolCalls, stopReason: "tool_use" }
}

/** Deterministic scripted adapter: last step repeats if the loop asks again. */
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

function lastToolOutput(messages: readonly LLMMessage[]): string {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i]
    if (message?.role === "tool") return message.content
  }
  return ""
}

describe("butler main chain (integration)", () => {
  let db: TestDb
  let wiring: Wiring
  let workspace: string
  const savedEnv: Record<string, string | undefined> = {}

  beforeEach(async () => {
    for (const key of ISOLATED_ENV_KEYS) {
      savedEnv[key] = process.env[key]
      delete process.env[key]
    }
    workspace = mkdtempSync(join(tmpdir(), "butler-main-chain-"))
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

  it("纯文本问答：回复可发送、Run succeeded、assistant 消息落库", async () => {
    const conversationId = "int-text"
    const result = await runTurn({
      conversationId,
      content: "你好",
      adapter: makeScriptedAdapter([() => textResponse("你好，我是你的管家。")]),
    })

    expect(result.reply).toContain("管家")
    const rows = await runsFor(conversationId)
    expect(rows).toHaveLength(1)
    expect(rows[0]?.status).toBe("succeeded")

    const messages = await wiring.runtimeStore.listMessages(conversationId)
    expect(messages.some((m) => m.role === "user" && m.content["text"] === "你好")).toBe(true)
    const assistant = messages.find((m) => m.role === "assistant")
    expect(String(assistant?.content["text"] ?? "")).toContain("管家")
  })

  it("write_file 全链路：待审批 → 确认 → 文件落盘、Run succeeded", async () => {
    const conversationId = "int-write"
    const content = "集成测试写入内容"
    const path = "hello.txt"
    const adapter = makeScriptedAdapter([
      () => toolCallResponse([{ id: "tc-write", name: "write_file", args: { path, content } }]),
    ])

    // Policy marks write_file alwaysConfirm, so the first turn pauses for the owner.
    const paused = await runTurn({
      conversationId,
      content: "把内容写到 hello.txt",
      allowedToolNames: ["write_file"],
      adapter,
    })
    expect(paused.reply).toContain("审批")

    const pending =
      await wiring.runtimeStore.listWaitingApprovalStepsForConversation(conversationId)
    expect(pending).toHaveLength(1)
    const runId = pending[0]?.runId
    expect(runId).toBeTruthy()
    expect(existsSync(join(workspace, path))).toBe(false)

    const confirmed = await runTurn({
      conversationId,
      content: "确认",
      allowedToolNames: ["write_file"],
      adapter,
    })
    expect(confirmed.reply).toContain("已写入")
    expect(readFileSync(join(workspace, path), "utf8")).toBe(content)

    const rows = await runsFor(conversationId)
    expect(rows).toHaveLength(1)
    expect(rows[0]?.runId).toBe(runId)
    expect(rows[0]?.status).toBe("succeeded")
  })

  it("read_file 全链路：文件内容进入用户回复、Run succeeded", async () => {
    const conversationId = "int-read"
    writeFileSync(join(workspace, "notes.txt"), "项目代号：青柠计划\n", "utf8")
    const adapter = makeScriptedAdapter([
      () => toolCallResponse([{ id: "tc-read", name: "read_file", args: { path: "notes.txt" } }]),
      (messages) => textResponse(`我读到了：${lastToolOutput(messages).trim()}`),
    ])

    const result = await runTurn({
      conversationId,
      content: "notes.txt 里写了什么？",
      allowedToolNames: ["read_file"],
      adapter,
    })

    expect(result.reply).toContain("青柠计划")
    const rows = await runsFor(conversationId)
    expect(rows[0]?.status).toBe("succeeded")
  })

  it("run_command 全链路：命令输出进入用户回复、Run succeeded", async () => {
    const conversationId = "int-command"
    const adapter = makeScriptedAdapter([
      () =>
        toolCallResponse([{ id: "tc-cmd", name: "run_command", args: { argv: ["echo", "ok"] } }]),
      (messages) => textResponse(`命令输出是：${lastToolOutput(messages).trim()}`),
    ])

    const result = await runTurn({
      conversationId,
      content: "运行 echo ok",
      allowedToolNames: ["run_command"],
      adapter,
    })

    expect(result.reply).toContain("ok")
    const rows = await runsFor(conversationId)
    expect(rows[0]?.status).toBe("succeeded")
  })

  it("工具失败可恢复：越界读文件失败后仍给出可读回复、Run succeeded", async () => {
    const conversationId = "int-tool-recover"
    const adapter = makeScriptedAdapter([
      () =>
        toolCallResponse([
          { id: "tc-escape", name: "read_file", args: { path: "../outside.txt" } },
        ]),
      (messages) =>
        textResponse(
          lastToolOutput(messages).includes("outside")
            ? "读取失败：该路径不在工作区内，请提供工作区内的文件。"
            : "读取完成。",
        ),
    ])

    const result = await runTurn({
      conversationId,
      content: "读一下 ../outside.txt",
      allowedToolNames: ["read_file"],
      adapter,
    })

    // Tool failure is a tool result, not a Run failure: the model still answers.
    expect(result.reply).toContain("工作区")
    const rows = await runsFor(conversationId)
    expect(rows[0]?.status).toBe("succeeded")
    const messages = await wiring.runtimeStore.listMessages(conversationId)
    expect(String(messages.find((m) => m.role === "assistant")?.content["text"] ?? "")).toContain(
      "工作区",
    )
  })

  it("write_file 越界：审批后工具失败不再终结 Run（F-09）", async () => {
    // A capability error is a tool result: the run continues (or falls back to
    // a readable reply) instead of being terminalized, and nothing lands outside
    // the workspace.
    const conversationId = "int-write-escape"
    const escapeName = `${basename(workspace)}-escape.txt`
    const adapter = makeScriptedAdapter([
      () =>
        toolCallResponse([
          {
            id: "tc-write-escape",
            name: "write_file",
            args: { path: `../${escapeName}`, content: "should not land" },
          },
        ]),
    ])

    const paused = await runTurn({
      conversationId,
      content: "写到工作区外面",
      allowedToolNames: ["write_file"],
      adapter,
    })
    expect(paused.reply).toContain("审批")

    const confirmed = await runTurn({
      conversationId,
      content: "确认",
      allowedToolNames: ["write_file"],
      adapter,
    })
    expect(confirmed.reply).toContain("没有完成")
    expect(existsSync(join(workspace, "..", escapeName))).toBe(false)

    // F-09: a tool-level failure is a result the model can explain, not a Run
    // terminalization; the conversation stays usable.
    const rows = await runsFor(conversationId)
    expect(rows[0]?.status).toBe("succeeded")
  })
})

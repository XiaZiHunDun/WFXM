import { mkdtemp, readFile, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { createTraceEvent } from "@butler/domain/observability/local-trace.js"
import { EventBridge } from "@butler/persistence/event-bridge.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { createTraceStore, type TraceStore } from "@butler/persistence"
import { makeTestDb, type TestDb } from "@butler/persistence/testing.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { makeWiring, type Wiring } from "./wiring.js"
import { parseWechatReplayCommand, tryWechatReplayCommand } from "./wechat-replay-commands.js"

const NOW = Date.UTC(2026, 10, 25, 1, 0, 0)
const OWNER_ENV = { BUTLER_OWNER_WECHAT_ID: "owner-1" } as NodeJS.ProcessEnv

describe("parseWechatReplayCommand", () => {
  it("parses /复盘 with default and clamped limits", () => {
    expect(parseWechatReplayCommand("/复盘")).toEqual({ kind: "list", limit: 5 })
    expect(parseWechatReplayCommand("/复盘 3")).toEqual({ kind: "list", limit: 3 })
    expect(parseWechatReplayCommand("/复盘 999")).toEqual({ kind: "list", limit: 20 })
    expect(parseWechatReplayCommand("/复盘 abc")).toEqual({ kind: "list", limit: 5 })
  })

  it("parses /转用例 and ignores unrelated text", () => {
    expect(parseWechatReplayCommand("/转用例 turn-172")).toEqual({
      kind: "to_scenario",
      token: "turn-172",
    })
    expect(parseWechatReplayCommand("/周报")).toBeNull()
    expect(parseWechatReplayCommand("复盘一下")).toBeNull()
  })
})

describe("tryWechatReplayCommand", () => {
  let db: TestDb
  let wiring: Wiring
  let traceStore: TraceStore
  let draftDir: string

  beforeEach(async () => {
    db = await makeTestDb()
    traceStore = createTraceStore(db.db)
    const runtimeStore = createRuntimeStore(db.db)
    wiring = makeWiring({
      bridge: new EventBridge({ db: db.db, workerId: "replay-test" }),
      workerId: "replay-test",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      backfillConversation: async () => undefined,
      traceStore,
    })
    draftDir = await mkdtemp(join(tmpdir(), "replay-drafts-"))
    await traceStore.append([
      createTraceEvent({
        kind: "step",
        name: "tool_write_file",
        status: "error",
        turnId: "turn-1720000000",
        detail: { tool: "write_file", code: "E-TOOL-02" },
        nowMs: NOW - 60 * 60 * 1000,
      }),
      createTraceEvent({
        kind: "run",
        name: "finish",
        status: "error",
        turnId: "turn-1720000000",
        detail: { code: "E-TOOL-02" },
        nowMs: NOW - 59 * 60 * 1000,
      }),
      createTraceEvent({
        kind: "run",
        name: "finish",
        status: "ok",
        turnId: "turn-ok",
        nowMs: NOW - 30 * 60 * 1000,
      }),
    ])
  })

  afterEach(async () => {
    await db.close()
    await rm(draftDir, { recursive: true, force: true })
  })

  function env(extra: Record<string, string> = {}): NodeJS.ProcessEnv {
    return { ...OWNER_ENV, BUTLER_V5_EVAL_DRAFT_DIR: draftDir, ...extra } as NodeJS.ProcessEnv
  }

  it("does not answer non-owners", async () => {
    const result = await tryWechatReplayCommand({
      wiring,
      fromUserId: "stranger",
      content: "/复盘",
      env: env(),
      nowMs: () => NOW,
    })
    expect(result).toBeNull()
  })

  it("lists only failed turns from the persisted store", async () => {
    const result = await tryWechatReplayCommand({
      wiring,
      fromUserId: "owner-1",
      content: "/复盘",
      env: env(),
      nowMs: () => NOW,
    })
    expect(result?.reply).toContain("最近失败 turn（1 个）")
    expect(result?.reply).toContain("[turn-172]")
    expect(result?.reply).toContain("E-TOOL-02")
    expect(result?.reply).toContain("write_file")
    expect(result?.traces[0]).toBe("wechat-replay: store 1")
  })

  it("writes a skipped scenario draft for /转用例", async () => {
    const result = await tryWechatReplayCommand({
      wiring,
      fromUserId: "owner-1",
      content: "/转用例 turn-1720000000",
      env: env(),
      nowMs: () => NOW,
    })
    expect(result?.reply).toContain("已生成回归草稿")
    expect(result?.traces[0]).toBe("wechat-replay: to-scenario turn-1720000000")

    const json = JSON.parse(await readFile(join(draftDir, "turn-1720000000.json"), "utf8")) as {
      observed: { runStatus: string; errorCode: string }
    }
    expect(json.observed.runStatus).toBe("failed")
    expect(json.observed.errorCode).toBe("E-TOOL-02")

    const test = await readFile(join(draftDir, "turn-1720000000.draft.test.ts"), "utf8")
    expect(test).toContain("describe.skip")
  })

  it("explains an unknown turn", async () => {
    const result = await tryWechatReplayCommand({
      wiring,
      fromUserId: "owner-1",
      content: "/转用例 turn-missing",
      env: env(),
      nowMs: () => NOW,
    })
    expect(result?.reply).toContain("未找到 turn turn-missing")
  })
})

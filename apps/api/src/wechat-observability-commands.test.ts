import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { createTraceEvent } from "@butler/domain/observability/local-trace.js"
import { EventBridge } from "@butler/persistence/event-bridge.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { createTraceStore, type TraceStore } from "@butler/persistence"
import { makeTestDb, type TestDb } from "@butler/persistence/testing.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { makeWiring, type Wiring } from "./wiring.js"
import {
  formatDiagnosticsReply,
  formatTraceLogReply,
  isWechatObservabilityOwner,
  parseWechatObservabilityCommand,
  tryWechatObservabilityCommand,
} from "./wechat-observability-commands.js"
import type { DiagnosticsReport } from "./diagnostics.js"

function diagnosticsReport(
  overrides: Partial<DiagnosticsReport["checks"]> = {},
): DiagnosticsReport {
  return {
    status: "ok",
    wiring: "v5",
    checks: {
      db: { status: "up", latency_ms: 2 },
      outbox: { pending: 0, failed: 0, oldest_pending_age_ms: null },
      approvals: { waiting: 0 },
      runs: { last_succeeded_at: null },
      traces: { memory: 3, pending_write: 0, dropped: 0, persisted: 42 },
      failures: { window_ms: 7 * 24 * 60 * 60 * 1000, total: 0, clusters: [] },
      ...overrides,
    },
    trace: {
      enabled: true,
      redact: true,
      maxEvents: 500,
      exporter: "off",
      retention_days: 30,
      max_rows: 200000,
    },
    eval_baseline: {
      dir: "/tmp/recordings",
      latest_at: null,
      age_days: null,
      stale: true,
      max_age_days: 30,
      count: 0,
    },
  }
}

describe("parseWechatObservabilityCommand", () => {
  it("recognizes /诊断 and its alias", () => {
    expect(parseWechatObservabilityCommand("/诊断")).toEqual({ kind: "diagnostics" })
    expect(parseWechatObservabilityCommand("  /diag ")).toEqual({ kind: "diagnostics" })
  })

  it("defaults /日志 to 10 lines and clamps explicit counts", () => {
    expect(parseWechatObservabilityCommand("/日志")).toEqual({ kind: "logs", limit: 10 })
    expect(parseWechatObservabilityCommand("/logs 20")).toEqual({ kind: "logs", limit: 20 })
    expect(parseWechatObservabilityCommand("/日志 999")).toEqual({ kind: "logs", limit: 50 })
    expect(parseWechatObservabilityCommand("/日志 0")).toEqual({ kind: "logs", limit: 10 })
    expect(parseWechatObservabilityCommand("/日志 abc")).toEqual({ kind: "logs", limit: 10 })
  })

  it("does not steal the existing /状态 project command or unrelated text", () => {
    expect(parseWechatObservabilityCommand("/状态")).toBeNull()
    expect(parseWechatObservabilityCommand("看看日志")).toBeNull()
    expect(parseWechatObservabilityCommand("/日志abc")).toBeNull()
  })
})

describe("isWechatObservabilityOwner", () => {
  it("fails closed without BUTLER_OWNER_WECHAT_ID", () => {
    expect(isWechatObservabilityOwner("owner-1", {} as NodeJS.ProcessEnv)).toBe(false)
  })

  it("accepts any id in the owner csv list", () => {
    const env = { BUTLER_OWNER_WECHAT_ID: "owner-1, owner-2" } as NodeJS.ProcessEnv
    expect(isWechatObservabilityOwner("owner-1", env)).toBe(true)
    expect(isWechatObservabilityOwner("owner-2", env)).toBe(true)
    expect(isWechatObservabilityOwner("stranger", env)).toBe(false)
  })
})

describe("formatDiagnosticsReply", () => {
  it("renders the healthy aggregate", () => {
    const reply = formatDiagnosticsReply(diagnosticsReport())
    expect(reply).toContain("【系统诊断】正常")
    expect(reply).toContain("数据库：正常（2ms）")
    expect(reply).toContain("待审批：0 条")
    expect(reply).toContain("轨迹：内存 3 · 待写 0 · 已存 42")
    expect(reply).toContain("失败（近 7 天）：0 次")
    expect(reply).toContain("基线：无录音")
    expect(reply).toContain("保留：30 天 / 200000 条")
  })

  it("surfaces failure clusters and a fresh baseline", () => {
    const reply = formatDiagnosticsReply({
      ...diagnosticsReport({
        failures: {
          window_ms: 604_800_000,
          total: 3,
          clusters: [{ key: "E-LLM-01 × write_file", count: 2 }],
        },
      }),
      eval_baseline: {
        dir: "/tmp/recordings",
        latest_at: new Date(Date.now() - 2 * 86_400_000).toISOString(),
        age_days: 2,
        stale: false,
        max_age_days: 30,
        count: 8,
      },
    })
    expect(reply).toContain("失败（近 7 天）：3 次 · E-LLM-01 × write_file（2）")
    expect(reply).toContain("基线：2 天前（8 条）· 新鲜")
  })

  it("marks degraded database and surfaces backlog age", () => {
    const reply = formatDiagnosticsReply({
      ...diagnosticsReport({
        db: { status: "down", latency_ms: 0 },
        outbox: { pending: 2, failed: 1, oldest_pending_age_ms: 5 * 60_000 },
      }),
      status: "degraded",
    })
    expect(reply).toContain("【系统诊断】降级")
    expect(reply).toContain("数据库：异常")
    expect(reply).toContain("待发消息：2 条（失败 1）")
    expect(reply).toContain("最久待发：5 分钟")
  })
})

describe("formatTraceLogReply", () => {
  const event = createTraceEvent({
    kind: "run",
    name: "failure",
    status: "error",
    turnId: "turn-1720000000",
    detail: { code: "E-LLM-01", reason: "connect ECONNREFUSED 127.0.0.1:1" },
    nowMs: Date.UTC(2026, 10, 24, 1, 2, 3),
  })

  it("shows clock, kind/name, status, short turn id and code — not the raw reason", () => {
    const reply = formatTraceLogReply([event], { source: "store", limit: 10 })
    expect(reply).toContain("run/failure error")
    expect(reply).toContain("[turn-172]")
    expect(reply).toContain("E-LLM-01")
    expect(reply).toContain("11-24 09:02:03")
    expect(reply).not.toContain("ECONNREFUSED")
  })

  it("explains disabled tracing and empty stores", () => {
    expect(formatTraceLogReply([], { source: "none", limit: 10 })).toContain("未启用")
    expect(formatTraceLogReply([], { source: "store", limit: 10 })).toBe("暂无轨迹记录。")
  })
})

describe("tryWechatObservabilityCommand", () => {
  let db: TestDb
  let wiring: Wiring
  let traceStore: TraceStore
  const env = { BUTLER_OWNER_WECHAT_ID: "owner-1" } as NodeJS.ProcessEnv

  beforeEach(async () => {
    db = await makeTestDb()
    traceStore = createTraceStore(db.db)
    const runtimeStore = createRuntimeStore(db.db)
    wiring = makeWiring({
      bridge: new EventBridge({ db: db.db, workerId: "obs-cmd-test" }),
      workerId: "obs-cmd-test",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      backfillConversation: async () => undefined,
      traceStore,
    })
  })

  afterEach(async () => {
    await db.close()
  })

  it("returns null for non-owners (falls through to normal intake)", async () => {
    const result = await tryWechatObservabilityCommand({
      wiring,
      fromUserId: "stranger",
      content: "/诊断",
      env,
    })
    expect(result).toBeNull()
  })

  it("returns null when the message is not an observability command", async () => {
    const result = await tryWechatObservabilityCommand({
      wiring,
      fromUserId: "owner-1",
      content: "帮我看看今天的任务",
      env,
    })
    expect(result).toBeNull()
  })

  it("renders diagnostics through collectDiagnostics", async () => {
    const result = await tryWechatObservabilityCommand({
      wiring,
      fromUserId: "owner-1",
      content: "/诊断",
      env,
    })
    expect(result).not.toBeNull()
    expect(result?.reply).toContain("【系统诊断】正常")
    expect(result?.traces[0]).toBe("wechat-diag: ok")
  })

  it("lists recent persisted traces for /日志", async () => {
    await traceStore.append([
      createTraceEvent({
        kind: "step",
        name: "llm_call",
        status: "error",
        turnId: "turn-1720000000",
        conversationId: "c-wechat-owner-1",
        detail: { code: "E-LLM-01" },
        nowMs: Date.UTC(2026, 10, 24, 1, 2, 3),
      }),
      createTraceEvent({
        kind: "run",
        name: "finish",
        turnId: "turn-1720000000",
        conversationId: "c-wechat-owner-1",
        nowMs: Date.UTC(2026, 10, 24, 1, 2, 4),
      }),
    ])

    const result = await tryWechatObservabilityCommand({
      wiring,
      fromUserId: "owner-1",
      content: "/日志 5",
      env,
    })
    expect(result?.reply).toContain("最近 2 条轨迹")
    expect(result?.reply).toContain("step/llm_call error [turn-172] E-LLM-01")
    expect(result?.traces[0]).toBe("wechat-logs: store 2")
  })
})

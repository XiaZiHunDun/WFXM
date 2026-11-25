import { join } from "node:path"
import { tmpdir } from "node:os"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { EventBridge } from "@butler/persistence/event-bridge.js"
import { conversations, createRuntimeStore, outbox } from "@butler/persistence"
import { makeTestDb, type TestDb } from "@butler/persistence/testing.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { resetSharedLocalTracer } from "@butler/runtime/observability/local-tracer.js"
import { makeWiring, type Wiring } from "./wiring.js"
import type { DiagnosticsReport } from "./diagnostics.js"
import {
  evaluateAlertSignals,
  parseAlertConfig,
  runHeartbeatTick,
  type AlertConfig,
} from "./observability-heartbeat.js"

const MISSING_DIR = join(tmpdir(), "wfxm-missing-recordings-do-not-create")

function report(overrides: Partial<DiagnosticsReport["checks"]> = {}): DiagnosticsReport {
  return {
    status: "ok",
    wiring: "v5",
    checks: {
      db: { status: "up", latency_ms: 1 },
      outbox: { pending: 0, failed: 0, oldest_pending_age_ms: null },
      approvals: { waiting: 0 },
      runs: { last_succeeded_at: null },
      traces: { memory: 0, pending_write: 0, dropped: 0, persisted: 0 },
      failures: { window_ms: 604_800_000, total: 0, clusters: [] },
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
      dir: MISSING_DIR,
      latest_at: null,
      age_days: null,
      stale: true,
      max_age_days: 30,
      count: 0,
    },
  }
}

const baseConfig = (overrides: Partial<AlertConfig> = {}): AlertConfig => ({
  enabled: true,
  intervalMs: 300_000,
  silenceMs: 6 * 60 * 60_000,
  failureThreshold: 20,
  to: "owner-1",
  ...overrides,
})

describe("parseAlertConfig", () => {
  it("defaults to enabled with no recipient", () => {
    expect(parseAlertConfig({} as NodeJS.ProcessEnv)).toEqual({
      enabled: true,
      intervalMs: 300_000,
      silenceMs: 6 * 60 * 60_000,
      failureThreshold: 20,
      to: null,
    })
  })

  it("accepts explicit values and falls back to the owner csv", () => {
    const config = parseAlertConfig({
      BUTLER_V5_ALERT_ENABLED: "0",
      BUTLER_V5_ALERT_INTERVAL_MS: "60000",
      BUTLER_V5_ALERT_SILENCE_MS: "900000",
      BUTLER_V5_ALERT_FAILURE_THRESHOLD: "3",
      BUTLER_OWNER_WECHAT_ID: "owner-1, owner-2",
    } as NodeJS.ProcessEnv)
    expect(config).toEqual({
      enabled: false,
      intervalMs: 60_000,
      silenceMs: 900_000,
      failureThreshold: 3,
      to: "owner-1",
    })
  })
})

describe("evaluateAlertSignals", () => {
  it("reports no signal for a healthy report", () => {
    expect(evaluateAlertSignals(report(), 20)).toEqual([])
  })

  it("derives one signal per broken dependency", () => {
    const signals = evaluateAlertSignals(
      report({
        db: { status: "down", latency_ms: 0 },
        outbox: { pending: 0, failed: 2, oldest_pending_age_ms: null },
        traces: { memory: 0, pending_write: 0, dropped: 4, persisted: 0 },
        failures: { window_ms: 604_800_000, total: 25, clusters: [{ key: "E-1 × x", count: 9 }] },
      }),
      20,
    )
    expect(signals.map((signal) => signal.key)).toEqual([
      "db_down",
      "outbox_failed",
      "trace_dropped",
      "failure_rate",
    ])
    expect(signals[3]?.text).toContain("最多：E-1 × x（9）")
  })

  it("only alerts on baseline staleness when recordings exist", () => {
    const withData = report()
    const stale = evaluateAlertSignals(
      {
        ...withData,
        eval_baseline: { ...withData.eval_baseline, count: 3, age_days: 40, stale: true },
      },
      20,
    )
    expect(stale.map((signal) => signal.key)).toContain("eval_baseline_stale")
    expect(evaluateAlertSignals(withData, 20)).toEqual([])
  })
})

describe("runHeartbeatTick", () => {
  let db: TestDb
  let wiring: Wiring
  const env = {
    BUTLER_V5_EVAL_RECORDINGS_DIR: MISSING_DIR,
  } as NodeJS.ProcessEnv

  beforeEach(async () => {
    resetSharedLocalTracer({ BUTLER_V5_TRACE: "0" })
    db = await makeTestDb()
    const runtimeStore = createRuntimeStore(db.db)
    wiring = makeWiring({
      bridge: new EventBridge({ db: db.db, workerId: "hb-test" }),
      workerId: "hb-test",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      backfillConversation: async () => undefined,
    })
  })

  afterEach(async () => {
    await db.close()
  })

  async function addFailedOutbox(): Promise<void> {
    const now = Date.now()
    await db.db.insert(conversations).values({
      conversationId: "c-hb",
      projectId: "p1",
      subject: "owner",
      createdAt: new Date(now - 10_000),
      updatedAt: new Date(now),
    })
    await db.db.insert(outbox).values({
      messageId: crypto.randomUUID(),
      streamId: "c-hb",
      aggregateType: "run",
      payload: {},
      status: "failed",
      attemptCount: 3,
      nextAttemptAt: new Date(now),
      createdAt: new Date(now - 20_000),
    })
  }

  it("stays quiet on a healthy system", async () => {
    const send = async () => ({ ok: true as const })
    const result = await runHeartbeatTick({
      wiring,
      env,
      config: baseConfig(),
      nowMs: Date.now(),
      send,
    })
    expect(result.reason).toBe("healthy")
    expect(result.sent).toBe(false)
  })

  it("sends once, then silences the same signal", async () => {
    await addFailedOutbox()
    const now = Date.now()
    const calls: string[] = []
    const send = async (input: { readonly text: string }) => {
      calls.push(input.text)
      return { ok: true as const }
    }
    const lastSent = new Map<string, number>()

    const first = await runHeartbeatTick({
      wiring,
      env,
      config: baseConfig(),
      nowMs: now,
      lastSent,
      send,
    })
    expect(first.reason).toBe("sent")
    expect(first.fresh.map((signal) => signal.key)).toEqual(["outbox_failed"])
    expect(calls[0]).toContain("待发消息失败 1 条")
    expect(lastSent.get("outbox_failed")).toBe(now)

    const second = await runHeartbeatTick({
      wiring,
      env,
      config: baseConfig(),
      nowMs: now + 60_000,
      lastSent,
      send,
    })
    expect(second.reason).toBe("silenced")

    const third = await runHeartbeatTick({
      wiring,
      env,
      config: baseConfig(),
      nowMs: now + 6 * 60 * 60_000,
      lastSent,
      send,
    })
    expect(third.reason).toBe("sent")
    expect(calls).toHaveLength(2)
  })

  it("never invents a recipient", async () => {
    await addFailedOutbox()
    let called = false
    const send = async () => {
      called = true
      return { ok: true as const }
    }
    const result = await runHeartbeatTick({
      wiring,
      env,
      config: baseConfig({ to: null }),
      nowMs: Date.now(),
      send,
    })
    expect(result.reason).toBe("no_recipient")
    expect(called).toBe(false)
  })

  it("reports send failures without marking the signal as sent", async () => {
    await addFailedOutbox()
    const lastSent = new Map<string, number>()
    const result = await runHeartbeatTick({
      wiring,
      env,
      config: baseConfig(),
      nowMs: Date.now(),
      lastSent,
      send: async () => ({ ok: false as const, reason: "network" }),
    })
    expect(result.reason).toBe("send_failed")
    expect(lastSent.size).toBe(0)
  })
})

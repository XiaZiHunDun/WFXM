import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { EventBridge } from "@butler/persistence/event-bridge.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { resetSharedLocalTracer } from "@butler/runtime/observability/local-tracer.js"
import { conversations, createRuntimeStore, outbox, runs, steps } from "@butler/persistence"
import { makeTestDb } from "@butler/persistence/testing.js"
import type { Wiring } from "./wiring.js"
import { makeWiring } from "./wiring.js"
import { collectDiagnostics } from "./diagnostics.js"

function makeWiringForTest(db: Awaited<ReturnType<typeof makeTestDb>>): Wiring {
  const bridge = new EventBridge({ db: db.db, workerId: "w-diag" })
  const runtimeStore = createRuntimeStore(db.db)
  return makeWiring({
    bridge,
    workerId: "w-diag",
    runtimeStore,
    runEngine: new RunEngine(runtimeStore),
    db: db.db,
    backfillConversation: async () => undefined,
  })
}

describe("collectDiagnostics", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let wiring: Wiring

  beforeEach(async () => {
    resetSharedLocalTracer({ BUTLER_V5_TRACE: "0" })
    db = await makeTestDb()
    wiring = makeWiringForTest(db)
  })

  afterEach(async () => {
    await db.close()
  })

  it("reports ok with zero counts on an empty database", async () => {
    const report = await collectDiagnostics(wiring, {}, 1_700_000_000_000)
    expect(report.status).toBe("ok")
    expect(report.wiring).toBe("v5")
    expect(report.checks.db.status).toBe("up")
    expect(report.checks.outbox).toEqual({
      pending: 0,
      failed: 0,
      oldest_pending_age_ms: null,
    })
    expect(report.checks.approvals.waiting).toBe(0)
    expect(report.checks.runs.last_succeeded_at).toBeNull()
    expect(report.trace.retention_days).toBe(30)
    expect(report.trace.max_rows).toBe(200000)
  })

  it("aggregates outbox, approvals and last successful run", async () => {
    const now = 1_700_000_000_000
    const conversationId = "c-diag-1"
    const runId = crypto.randomUUID()
    await db.db.insert(conversations).values({
      conversationId,
      projectId: "p1",
      subject: "owner",
      createdAt: new Date(now - 10_000),
      updatedAt: new Date(now),
    })
    await db.db.insert(runs).values({
      runId,
      conversationId,
      triggerSource: "wechat",
      idempotencyKey: "diag-run-1",
      subject: "owner",
      goal: "test",
      status: "succeeded",
      budget: {},
      version: 2,
      createdAt: new Date(now - 5_000),
      updatedAt: new Date(now - 1_000),
    })
    await db.db.insert(steps).values({
      stepId: crypto.randomUUID(),
      runId,
      kind: "approval",
      status: "waiting",
      input: {},
      createdAt: new Date(now - 4_000),
      updatedAt: new Date(now - 4_000),
    })
    await db.db.insert(outbox).values([
      {
        messageId: crypto.randomUUID(),
        streamId: conversationId,
        aggregateType: "run",
        payload: {},
        status: "pending",
        attemptCount: 0,
        nextAttemptAt: new Date(now),
        createdAt: new Date(now - 30_000),
      },
      {
        messageId: crypto.randomUUID(),
        streamId: conversationId,
        aggregateType: "run",
        payload: {},
        status: "failed",
        attemptCount: 3,
        nextAttemptAt: new Date(now),
        createdAt: new Date(now - 20_000),
      },
    ])

    const report = await collectDiagnostics(wiring, {}, now)
    expect(report.status).toBe("ok")
    expect(report.checks.outbox.pending).toBe(1)
    expect(report.checks.outbox.failed).toBe(1)
    expect(report.checks.outbox.oldest_pending_age_ms).toBe(30_000)
    expect(report.checks.approvals.waiting).toBe(1)
    expect(report.checks.runs.last_succeeded_at).toBe(new Date(now - 1_000).toISOString())
  })

  it("degrades to ok for a wiring stub without db", async () => {
    const report = await collectDiagnostics({ version: "v5" } as never, {}, 1)
    expect(report.status).toBe("ok")
    expect(report.checks.db.status).toBe("up")
    expect(report.checks.outbox.pending).toBe(0)
    expect(report.checks.traces.persisted).toBeNull()
  })
})

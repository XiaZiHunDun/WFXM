import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { createTraceEvent } from "@butler/domain/observability/local-trace.js"
import { makeTestDb, type TestDb } from "./testing.js"
import { createTraceStore } from "./trace-store.js"

const DAY_MS = 24 * 60 * 60 * 1000

describe("traceStore", () => {
  let db: TestDb

  beforeEach(async () => {
    db = await makeTestDb()
  })

  afterEach(async () => {
    await db.close()
  })

  it("appends and lists rows in chronological order", async () => {
    const store = createTraceStore(db.db)
    await store.append([])
    expect(await store.count()).toBe(0)

    const a = createTraceEvent({ kind: "run", name: "inbound", runId: "r1", nowMs: 1000 })
    const b = createTraceEvent({
      kind: "step",
      name: "llm_call",
      runId: "r1",
      turnId: "turn-1",
      nowMs: 2000,
      token: { inputTokens: 3, outputTokens: 4, totalTokens: 7 },
      costUsd: 0.02,
    })
    await store.append([a, b])

    const rows = await store.list({ runId: "r1" })
    expect(rows.map((e) => e.name)).toEqual(["inbound", "llm_call"])
    expect(rows[1]?.turnId).toBe("turn-1")
    expect(rows[1]?.token).toEqual({ inputTokens: 3, outputTokens: 4, totalTokens: 7 })
    expect(rows[1]?.costUsd).toBeCloseTo(0.02)
    expect(await store.count()).toBe(2)
    expect((await store.oldestCreatedAt())?.getTime()).toBe(1000)
  })

  it("filters by runId / conversationId / turnId / kind and limit", async () => {
    const store = createTraceStore(db.db)
    await store.append([
      createTraceEvent({
        kind: "run",
        name: "a",
        runId: "r1",
        conversationId: "c1",
        turnId: "turn-1",
        nowMs: 1,
      }),
      createTraceEvent({
        kind: "step",
        name: "b",
        runId: "r1",
        conversationId: "c2",
        turnId: "turn-2",
        nowMs: 2,
      }),
      createTraceEvent({
        kind: "policy",
        name: "c",
        runId: "r2",
        conversationId: "c2",
        turnId: "turn-2",
        nowMs: 3,
      }),
    ])

    expect((await store.list({ runId: "r1" })).map((e) => e.name)).toEqual(["a", "b"])
    expect((await store.list({ conversationId: "c2" })).map((e) => e.name)).toEqual(["b", "c"])
    expect((await store.list({ turnId: "turn-2" })).map((e) => e.name)).toEqual(["b", "c"])
    expect((await store.list({ kind: "policy" })).map((e) => e.name)).toEqual(["c"])
    expect((await store.list({ limit: 1 })).map((e) => e.name)).toEqual(["c"])
    expect(await store.list({ limit: 0 })).toEqual([])
  })

  it("prunes by age and by max rows", async () => {
    const store = createTraceStore(db.db)
    const now = 10 * DAY_MS
    await store.append([
      createTraceEvent({ kind: "run", name: "old", nowMs: now - 9 * DAY_MS }),
      createTraceEvent({ kind: "run", name: "e1", nowMs: now - 3000 }),
      createTraceEvent({ kind: "run", name: "e2", nowMs: now - 2000 }),
      createTraceEvent({ kind: "run", name: "e3", nowMs: now - 1000 }),
    ])

    const aged = await store.prune({ retentionDays: 3, maxRows: 0, nowMs: now })
    expect(aged.deletedByAge).toBe(1)
    expect(aged.deletedByRows).toBe(0)
    expect((await store.list()).map((e) => e.name)).toEqual(["e1", "e2", "e3"])

    const capped = await store.prune({ retentionDays: 30, maxRows: 2, nowMs: now })
    expect(capped.deletedByRows).toBe(1)
    expect((await store.list()).map((e) => e.name)).toEqual(["e2", "e3"])
    expect(await store.count()).toBe(2)
  })

  it("prune is a no-op on an empty table", async () => {
    const store = createTraceStore(db.db)
    expect(await store.prune({ retentionDays: 30, maxRows: 100, nowMs: Date.now() })).toEqual({
      deletedByAge: 0,
      deletedByRows: 0,
    })
    expect(await store.oldestCreatedAt()).toBeNull()
  })
})

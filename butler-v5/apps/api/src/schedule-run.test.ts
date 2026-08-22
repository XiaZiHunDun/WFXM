import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { eq } from "drizzle-orm"
import { EventBridge } from "@butler/runtime/bridge.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { runs } from "@butler/persistence/schema.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import { makeWiring, type Wiring } from "./wiring.js"
import { runScheduleJob } from "./schedule-run.js"
import { runScheduleTick } from "./schedule-worker.js"
import type { ScheduleJobSpec } from "@butler/domain/runtime.js"

const job = (over: Partial<ScheduleJobSpec> = {}): ScheduleJobSpec => ({
  id: "heartbeat",
  everyMs: 60_000,
  goal: "只读巡检，无事回复无事",
  cooldownMs: 1_000,
  maxSteps: 3,
  deadlineMs: 120_000,
  quietSuccess: true,
  enabled: true,
  ...over,
})

describe("schedule run + tick", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let wiring: Wiring

  beforeEach(async () => {
    db = await makeTestDb()
    const bridge = new EventBridge({ db: db.db, workerId: "w-sched" })
    const runtimeStore = createRuntimeStore(db.db)
    wiring = makeWiring({
      bridge,
      workerId: "w-sched",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      backfillConversation: async () => undefined,
    })
  })

  afterEach(async () => {
    await db.close()
  })

  it("persists schedule RunTrigger and deadline", async () => {
    const conversationId = "schedule-heartbeat"
    await runScheduleJob({
      wiring,
      job: job(),
      conversationId,
      idempotencyKey: "schedule:heartbeat:120000",
      deadline: new Date("2026-08-21T12:02:00Z"),
      env: {},
    })
    const [run] = await db.select().from(runs).where(eq(runs.conversationId, conversationId))
    expect(run?.triggerSource).toBe("schedule")
    expect(run?.subject).toBe("system:scheduler")
    expect(run?.budget).toMatchObject({
      maxSteps: 3,
      trustLevel: "trusted",
      triggerPayload: expect.objectContaining({ jobId: "heartbeat" }),
    })
    expect(run?.deadline?.toISOString()).toBe("2026-08-21T12:02:00.000Z")
  })

  it("defers when conversation already has an active main Run", async () => {
    const conversationId = "schedule-heartbeat"
    const createdAt = new Date("2026-08-21T00:00:00Z")
    await wiring.runtimeStore.createConversationWithUserMessage({
      conversationId,
      messageId: crypto.randomUUID(),
      subject: "system:scheduler",
      content: { text: "busy" },
      triggerSource: "schedule",
      idempotencyKey: "seed-busy",
      createdAt,
    })
    const run = await wiring.runtimeStore.createRun({
      id: crypto.randomUUID(),
      conversationId,
      parentRunId: null,
      triggerSource: "schedule",
      idempotencyKey: "seed-busy:run",
      subject: "system:scheduler",
      goal: "hold",
      budget: { maxSteps: 3 },
      deadline: null,
      createdAt,
    })
    await wiring.runtimeStore.transitionRunStatus(run.id, run.version, "running", new Date())

    const stats = await runScheduleTick({
      wiring,
      jobs: [job({ conversationId })],
      nowMs: () => 125_000,
      lastAttemptByJob: new Map(),
      scheduleInFlight: { value: false },
      isMainQueueBusy: () => false,
      env: {},
      logger: { info: () => undefined, warn: () => undefined, error: () => undefined },
    })
    expect(stats.deferred).toBe(1)
    expect(stats.fired).toBe(0)
  })
})

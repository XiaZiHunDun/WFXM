import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import {
  cancelRun,
  enterWaitingExternal,
  expireOverdueRuns,
  expireRun,
  resumeFromWaitingExternal,
} from "./run-lifecycle.js"

describe("run-lifecycle", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>

  beforeEach(async () => {
    db = await makeTestDb()
  })

  afterEach(async () => {
    await db.close()
  })

  async function seedRunningRun(opts: { deadline?: Date | null } = {}) {
    const store = createRuntimeStore(db.db)
    const createdAt = new Date("2026-08-20T00:00:00Z")
    const inbound = await store.createConversationWithUserMessage({
      conversationId: crypto.randomUUID(),
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "hi" },
      triggerSource: "channel",
      idempotencyKey: crypto.randomUUID(),
      createdAt,
    })
    const run = await store.createRun({
      id: crypto.randomUUID(),
      conversationId: inbound.conversationId,
      parentRunId: null,
      triggerSource: "channel",
      idempotencyKey: crypto.randomUUID(),
      subject: "owner-1",
      goal: "reply",
      budget: { maxSteps: 5 },
      deadline: opts.deadline === undefined ? null : opts.deadline,
      createdAt,
    })
    const running = await store.transitionRunStatus(run.id, run.version, "running", createdAt)
    return { store, run: running, conversationId: inbound.conversationId }
  }

  it("cancelRun transitions running -> cancelled", async () => {
    const { store, run } = await seedRunningRun()
    const cancelled = await cancelRun(store, run.id, { subject: "owner-1", reason: "test" })
    expect(cancelled.status).toBe("cancelled")
    expect(cancelled.version).toBe(run.version + 1)
  })

  it("expireRun marks past-deadline runs expired", async () => {
    const past = new Date("2026-08-19T00:00:00Z")
    const { store, run } = await seedRunningRun({ deadline: past })
    const expired = await expireRun(store, run.id, {
      now: new Date("2026-08-21T00:00:00Z"),
      subject: "system",
    })
    expect(expired.status).toBe("expired")
  })

  it("expireOverdueRuns sweeps active past-deadline runs", async () => {
    const past = new Date("2026-08-19T00:00:00Z")
    const { store, run } = await seedRunningRun({ deadline: past })
    const expired = await expireOverdueRuns(store, {
      now: new Date("2026-08-21T00:00:00Z"),
    })
    expect(expired.some((r) => r.id === run.id)).toBe(true)
    const updated = await store.getRun(run.id)
    expect(updated?.status).toBe("expired")
  })

  it("enterWaitingExternal and resumeFromWaitingExternal round-trip", async () => {
    const { store, run, conversationId } = await seedRunningRun()
    const { stepId, run: waiting } = await enterWaitingExternal(store, {
      runId: run.id,
      conversationId,
      subject: "owner-1",
      reason: "await webhook",
    })
    expect(waiting.status).toBe("waiting_external")
    const step = await store.getStep(stepId)
    expect(step?.kind).toBe("external")
    expect(step?.status).toBe("waiting")

    const resumed = await resumeFromWaitingExternal(store, run.id, {
      subject: "owner-1",
      stepId,
    })
    expect(resumed.status).toBe("running")
    const done = await store.getStep(stepId)
    expect(done?.status).toBe("succeeded")
  })
})

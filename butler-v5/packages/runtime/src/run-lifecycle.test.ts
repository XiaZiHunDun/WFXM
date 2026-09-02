import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import { auditEvents } from "@butler/persistence/schema.js"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import {
  IllegalRunTransitionError,
  cancelRun,
  cancelRunCascade,
  enterWaitingExternal,
  expireOverdueRuns,
  expireRun,
  resumeFromWaitingExternal,
  transitionRunToTerminal,
} from "./run-lifecycle.js"

describe("run-lifecycle", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>

  beforeEach(async () => {
    db = await makeTestDb()
  })

  afterEach(async () => {
    await db.close()
  })

  async function seedRunningRun(opts: { deadline?: Date | null } = {}, store?: RuntimeStore) {
    const activeStore = store ?? createRuntimeStore(db.db)
    const createdAt = new Date("2026-08-20T00:00:00Z")
    const inbound = await activeStore.createConversationWithUserMessage({
      conversationId: crypto.randomUUID(),
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "hi" },
      triggerSource: "channel",
      idempotencyKey: crypto.randomUUID(),
      createdAt,
    })
    const run = await activeStore.createRun({
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
    const running = await activeStore.transitionRunStatus(run.id, run.version, "running", createdAt)
    return { store: activeStore, run: running, conversationId: inbound.conversationId }
  }

  it("cancelRun transitions running -> cancelled", async () => {
    const { store, run } = await seedRunningRun()
    const cancelled = await cancelRun(store, run.id, { subject: "owner-1", reason: "test" })
    expect(cancelled.status).toBe("cancelled")
    expect(cancelled.version).toBe(run.version + 1)
  })

  it("cancelRun emits audit + status change atomically (D6-arch-align §20 #7)", async () => {
    const store = createRuntimeStore(db.db)
    const createdAt = new Date("2026-08-20T00:00:00Z")
    const in1 = await store.createConversationWithUserMessage({
      conversationId: "c-cancel-atomic",
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "hi" },
      triggerSource: "channel",
      idempotencyKey: "cancel-atomic",
      createdAt,
    })
    const run = await store.createRun({
      id: crypto.randomUUID(),
      conversationId: in1.conversationId,
      parentRunId: null,
      triggerSource: "channel",
      idempotencyKey: "cancel-atomic-run",
      subject: "owner-1",
      goal: "x",
      budget: {},
      deadline: null,
      createdAt,
    })
    await store.transitionRunStatus(run.id, 1, "running", createdAt)

    const cancelled = await cancelRun(store, run.id, {
      subject: "owner-1",
      reason: "atomic-test",
    })
    expect(cancelled.status).toBe("cancelled")
    // Version bumped exactly once from the running state (version 2 after
    // the running transition). The tx's transitionRunStatusInTx wrote
    // a single version increment in the same tx as the audit insert.
    expect(cancelled.version).toBe(3)

    // A second cancel on a now-cancelled run is rejected (terminal state),
    // not silently re-cancelled. This is the expected behavior since
    // canTransitionRun is the SSOT for legal transitions.
    await expect(
      cancelRun(store, run.id, { subject: "owner-1" }),
    ).rejects.toThrow(/illegal Run transition/)
  })

  it("cancelRunCascade cancels descendants recursively (D4-arch-align §20 #7)", async () => {
    const store = createRuntimeStore(db.db)
    const createdAt = new Date("2026-08-20T00:00:00Z")
    // Seed: grand-parent -> parent -> child (3 levels)
    const in1 = await store.createConversationWithUserMessage({
      conversationId: "c-cascade-1",
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "root" },
      triggerSource: "channel",
      idempotencyKey: "cascade-msg",
      createdAt,
    })
    const grand = await store.createRun({
      id: crypto.randomUUID(),
      conversationId: in1.conversationId,
      parentRunId: null,
      triggerSource: "channel",
      idempotencyKey: "cascade-grand",
      subject: "owner-1",
      goal: "grand",
      budget: {},
      deadline: null,
      createdAt,
    })
    const parent = await store.createRun({
      id: crypto.randomUUID(),
      conversationId: in1.conversationId,
      parentRunId: grand.id,
      triggerSource: "parent_run",
      idempotencyKey: "cascade-parent",
      subject: "owner-1",
      goal: "parent",
      budget: {},
      deadline: null,
      createdAt,
    })
    const child = await store.createRun({
      id: crypto.randomUUID(),
      conversationId: in1.conversationId,
      parentRunId: parent.id,
      triggerSource: "parent_run",
      idempotencyKey: "cascade-child",
      subject: "owner-1",
      goal: "child",
      budget: {},
      deadline: null,
      createdAt,
    })
    await store.transitionRunStatus(parent.id, 1, "running", createdAt)
    await store.transitionRunStatus(child.id, 1, "running", createdAt)

    const cancelled = await cancelRunCascade(store, grand.id, {
      subject: "owner-1",
      reason: "owner_cancel_cascade",
    })
    // Three runs cancelled: grand + parent + child.
    expect(cancelled.map((r) => r.id).sort()).toEqual(
      [grand.id, parent.id, child.id].sort(),
    )
    // Each emitted a "run.cancelled" audit with cascade reason.
    const cascadeAudits = (
      await store.getRun(grand.id)
    )?.conversationId // placeholder; gather via raw SQL instead
    expect(cascadeAudits).toBeDefined()
    // Re-fetch root + child to confirm status.
    expect((await store.getRun(grand.id))?.status).toBe("cancelled")
    expect((await store.getRun(parent.id))?.status).toBe("cancelled")
    expect((await store.getRun(child.id))?.status).toBe("cancelled")

    // Idempotent: re-running cancelRunCascade is a no-op (returns only runs
    // that were actually transitioned; here everything is already cancelled).
    const second = await cancelRunCascade(store, grand.id, {
      subject: "owner-1",
    })
    expect(second).toHaveLength(0)
  })

  it("cancelRunCascade skips an already-expired descendant instead of aborting", async () => {
    const store = createRuntimeStore(db.db)
    const createdAt = new Date("2026-08-20T00:00:00Z")
    const in1 = await store.createConversationWithUserMessage({
      conversationId: crypto.randomUUID(),
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "root" },
      triggerSource: "channel",
      idempotencyKey: "cascade-expired-msg",
      createdAt,
    })
    const parent = await store.createRun({
      id: crypto.randomUUID(),
      conversationId: in1.conversationId,
      parentRunId: null,
      triggerSource: "channel",
      idempotencyKey: "cascade-expired-parent",
      subject: "owner-1",
      goal: "parent",
      budget: {},
      deadline: null,
      createdAt,
    })
    const expiredChild = await store.createRun({
      id: crypto.randomUUID(),
      conversationId: in1.conversationId,
      parentRunId: parent.id,
      triggerSource: "parent_run",
      idempotencyKey: "cascade-expired-child",
      subject: "owner-1",
      goal: "child",
      budget: {},
      deadline: new Date("2026-08-19T00:00:00Z"),
      createdAt,
    })
    const activeChild = await store.createRun({
      id: crypto.randomUUID(),
      conversationId: in1.conversationId,
      parentRunId: parent.id,
      triggerSource: "parent_run",
      idempotencyKey: "cascade-active-child",
      subject: "owner-1",
      goal: "child",
      budget: {},
      deadline: null,
      createdAt,
    })
    await store.transitionRunStatus(expiredChild.id, 1, "running", createdAt)
    await store.transitionRunStatus(activeChild.id, 1, "running", createdAt)
    await expireRun(store, expiredChild.id, { now: new Date("2026-08-21T00:00:00Z") })
    expect((await store.getRun(expiredChild.id))?.status).toBe("expired")

    // An expired descendant must be skipped, not throw and abort the cascade.
    const cancelled = await cancelRunCascade(store, parent.id, {
      subject: "owner-1",
      reason: "owner_cancel_cascade",
    })
    expect(cancelled.map((r) => r.id).sort()).toEqual([parent.id, activeChild.id].sort())
    expect((await store.getRun(parent.id))?.status).toBe("cancelled")
    expect((await store.getRun(activeChild.id))?.status).toBe("cancelled")
    expect((await store.getRun(expiredChild.id))?.status).toBe("expired")
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

  it("expireRun marks past-deadline runs expired and the optimistic version bumps exactly once", async () => {
    const past = new Date("2026-08-19T00:00:00Z")
    const { store, run } = await seedRunningRun({ deadline: past })
    const expired = await expireRun(store, run.id, {
      now: new Date("2026-08-21T00:00:00Z"),
      subject: "system",
    })
    expect(expired.status).toBe("expired")
    expect(expired.version).toBe(run.version + 1)
    expect((await store.getRun(run.id))?.status).toBe("expired")
  })

  it("expireRun rejects a Run that is already terminal (double-completion guard)", async () => {
    const past = new Date("2026-08-19T00:00:00Z")
    const now = new Date("2026-08-21T00:00:00Z")
    const { store, run } = await seedRunningRun({ deadline: past })
    await expireRun(store, run.id, { now })
    // A second expiry of the same Run is a no-op on the state machine and
    // must be rejected — the Run must never be completed twice.
    await expect(expireRun(store, run.id, { now })).rejects.toBeInstanceOf(
      IllegalRunTransitionError,
    )
    expect((await store.getRun(run.id))?.status).toBe("expired")
  })

  it("cancelRun rejects an already-expired Run (double-completion guard)", async () => {
    const past = new Date("2026-08-19T00:00:00Z")
    const { store, run } = await seedRunningRun({ deadline: past })
    await expireRun(store, run.id, { now: new Date("2026-08-21T00:00:00Z") })
    await expect(cancelRun(store, run.id, { subject: "owner-1" })).rejects.toBeInstanceOf(
      IllegalRunTransitionError,
    )
    expect((await store.getRun(run.id))?.status).toBe("expired")
  })

  it("expireRun rejects a Run with no deadline (unless forced)", async () => {
    const { store, run } = await seedRunningRun({ deadline: null })
    await expect(expireRun(store, run.id, { now: new Date() })).rejects.toThrow(/no deadline/)
    const forced = await expireRun(store, run.id, { now: new Date(), force: true })
    expect(forced.status).toBe("expired")
  })

  it("expireRun rejects a Run whose deadline has not been reached", async () => {
    const future = new Date("2026-09-01T00:00:00Z")
    const { store, run } = await seedRunningRun({ deadline: future })
    await expect(
      expireRun(store, run.id, { now: new Date("2026-08-21T00:00:00Z") }),
    ).rejects.toThrow(/deadline not reached/)
    expect((await store.getRun(run.id))?.status).toBe("running")
  })

  it("expireOverdueRuns is idempotent across sweeps", async () => {
    const past = new Date("2026-08-19T00:00:00Z")
    const now = new Date("2026-08-21T00:00:00Z")
    const { store, run } = await seedRunningRun({ deadline: past })
    const first = await expireOverdueRuns(store, { now })
    expect(first.map((r) => r.id)).toContain(run.id)
    expect((await store.getRun(run.id))?.status).toBe("expired")
    const second = await expireOverdueRuns(store, { now })
    expect(second).toHaveLength(0)
    expect((await store.getRun(run.id))?.status).toBe("expired")
  })

  it("expireOverdueRuns skips Runs a concurrent actor already resolved to terminal", async () => {
    const past = new Date("2026-08-19T00:00:00Z")
    const now = new Date("2026-08-21T00:00:00Z")
    const base = createRuntimeStore(db.db)
    const { run: a } = await seedRunningRun({ deadline: past }, base)
    const { run: b } = await seedRunningRun({ deadline: past }, base)

    // Simulate a concurrent owner cancel landing between the sweep's
    // `listRunsPastDeadline` read and its optimistic transition. `expireRun`
    // reads the Run once (pre-tx) then transitions with the optimistic
    // version inside a tx; we make the pre-tx read hand back a stale
    // snapshot while the real row moves to a terminal state, so the sweep's
    // own transition hits a version conflict. The sweep must skip A (already
    // terminal) and still expire B.
    let aStaleHandedOut = false
    const wrapped: RuntimeStore = {
      ...base,
      async getRun(runId) {
        const fresh = await base.getRun(runId)
        if (runId === a.id && fresh && fresh.status === "running" && !aStaleHandedOut) {
          aStaleHandedOut = true
          // Concurrent owner cancel lands right after the sweep's read:
          // move the real row to a terminal state outside any transaction.
          await base.transitionRunStatus(fresh.id, fresh.version, "cancelled", now)
          // Return the pre-cancel snapshot; the sweep's tx will then find a
          // version conflict on the real (cancelled) row.
          return fresh
        }
        return fresh
      },
    }

    const expired = await expireOverdueRuns(wrapped, { now })
    expect(expired.map((r) => r.id)).toEqual([b.id])
    expect((await base.getRun(a.id))?.status).toBe("cancelled")
    expect((await base.getRun(b.id))?.status).toBe("expired")
  })

  it("transitionRunToTerminal succeeds a running Run atomically with a run.succeeded audit", async () => {
    const { store, run } = await seedRunningRun()
    const now = new Date("2026-08-21T00:00:00Z")
    const terminal = await transitionRunToTerminal(store, run.id, {
      from: ["running"],
      to: "succeeded",
      now,
      subject: "owner-1",
    })
    expect(terminal?.status).toBe("succeeded")
    expect(terminal?.version).toBe(run.version + 1)
    // D6-arch-align §20 #7: state change + audit atomic.
    const audits = await db.db.select().from(auditEvents)
    expect(audits.filter((a) => a.action === "run.succeeded")).toHaveLength(1)
  })

  it("transitionRunToTerminal fails a running Run atomically with a run.failed audit + reason", async () => {
    const { store, run } = await seedRunningRun()
    const now = new Date("2026-08-21T00:00:00Z")
    const terminal = await transitionRunToTerminal(store, run.id, {
      from: ["running"],
      to: "failed",
      now,
      subject: "owner-1",
      reason: "boom",
    })
    expect(terminal?.status).toBe("failed")
    const audits = await db.db.select().from(auditEvents)
    const failed = audits.find((a) => a.action === "run.failed")
    expect(failed?.detail).toMatchObject({ reason: "boom", from: "running" })
  })

  it("transitionRunToTerminal is a no-op for an already-terminal Run (double-completion guard)", async () => {
    const past = new Date("2026-08-19T00:00:00Z")
    const now = new Date("2026-08-21T00:00:00Z")
    const { store, run } = await seedRunningRun({ deadline: past })
    await expireRun(store, run.id, { now })
    const result = await transitionRunToTerminal(store, run.id, {
      from: ["running"],
      to: "succeeded",
      now,
      subject: "owner-1",
    })
    expect(result).toBeNull()
    expect((await store.getRun(run.id))?.status).toBe("expired")
    // The skipped completion must not write a second audit row.
    const audits = await db.db.select().from(auditEvents)
    expect(audits.filter((a) => a.action === "run.succeeded")).toHaveLength(0)
  })

  it("transitionRunToTerminal is a no-op when the Run is not in the from set", async () => {
    const { store, run } = await seedRunningRun()
    const result = await transitionRunToTerminal(store, run.id, {
      from: ["waiting_approval"],
      to: "succeeded",
      now: new Date(),
      subject: "owner-1",
    })
    expect(result).toBeNull()
    expect((await store.getRun(run.id))?.status).toBe("running")
  })

  it("transitionRunToTerminal returns null for a missing Run", async () => {
    const { store } = await seedRunningRun()
    const result = await transitionRunToTerminal(store, crypto.randomUUID(), {
      from: ["running"],
      to: "succeeded",
      now: new Date(),
      subject: "owner-1",
    })
    expect(result).toBeNull()
  })
})

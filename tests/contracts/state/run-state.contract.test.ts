// 锚定契约：Run 状态机合法/非法迁移、终态不可回退、双重完成、乐观版本冲突、过期与取消级联（外部可观察的返回值与 DB 终态）。
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import {
  canTransitionRun,
  isTerminalRunStatus,
  transitionRun,
  TERMINAL_RUN_STATUSES,
  type Run,
  type RunStatus,
  type RuntimeStore,
  type StoredRun,
} from "../../../packages/domain/src/runtime/index.js"
import {
  createRuntimeStore,
  RuntimeVersionConflictError,
} from "../../../packages/persistence/src/runtime-store.js"
import { makeTestDb } from "../../../packages/persistence/src/testing.js"
import {
  IllegalRunTransitionError,
  cancelRun,
  cancelRunCascade,
  expireOverdueRuns,
  expireRun,
  transitionRunToTerminal,
} from "../../../packages/runtime/src/run-lifecycle.js"

const BASE_AT = new Date("2026-10-01T00:00:00.000Z")
const at = (offsetSeconds: number): Date => new Date(BASE_AT.getTime() + offsetSeconds * 1000)

const ALL_STATUSES: readonly RunStatus[] = [
  "queued",
  "running",
  "waiting_approval",
  "waiting_external",
  "succeeded",
  "failed",
  "cancelled",
  "expired",
]

/** 源码实际定义的合法边（packages/domain/src/runtime/transitions.ts）。 */
const LEGAL_EDGES: readonly (readonly [RunStatus, RunStatus])[] = [
  ["queued", "running"],
  ["queued", "cancelled"],
  ["queued", "expired"],
  ["running", "waiting_approval"],
  ["running", "waiting_external"],
  ["running", "succeeded"],
  ["running", "failed"],
  ["running", "cancelled"],
  ["running", "expired"],
  ["waiting_approval", "running"],
  ["waiting_approval", "failed"],
  ["waiting_approval", "cancelled"],
  ["waiting_approval", "expired"],
  ["waiting_external", "running"],
  ["waiting_external", "failed"],
  ["waiting_external", "cancelled"],
  ["waiting_external", "expired"],
]

const ILLEGAL_EDGES: readonly (readonly [RunStatus, RunStatus])[] = [
  ...TERMINAL_RUN_STATUSES.flatMap((terminal) => ALL_STATUSES.map((to) => [terminal, to] as const)),
  ["queued", "waiting_approval"],
  ["queued", "waiting_external"],
  ["queued", "succeeded"],
  ["queued", "failed"],
  ["running", "queued"],
  ["waiting_approval", "waiting_external"],
  ["waiting_approval", "succeeded"],
  ["waiting_external", "waiting_approval"],
  ["waiting_external", "succeeded"],
]

/** 从 queued 出发的合法播种路径，确保 DB 行由状态机而非直写伪造。 */
const PATH_TO: Readonly<Record<RunStatus, readonly RunStatus[]>> = {
  queued: [],
  running: ["running"],
  waiting_approval: ["running", "waiting_approval"],
  waiting_external: ["running", "waiting_external"],
  succeeded: ["running", "succeeded"],
  failed: ["running", "failed"],
  cancelled: ["running", "cancelled"],
  expired: ["running", "expired"],
}

function makeDomainRun(status: RunStatus): Run {
  return {
    id: "run-contract",
    conversationId: "conv-contract",
    parentRunId: null,
    trigger: {
      subject: "owner-contract",
      source: "channel",
      conversationRef: "conv-contract",
      payload: {},
      trustLevel: "trusted",
      idempotencyKey: "trigger-contract",
    },
    goal: "reply",
    budget: { maxSteps: 5 },
    deadline: null,
    status,
    version: 1,
    createdAt: 0,
    updatedAt: 0,
  }
}

describe("Run state machine contract", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let store: RuntimeStore

  beforeEach(async () => {
    db = await makeTestDb()
    store = createRuntimeStore(db)
  })

  afterEach(async () => {
    await db.close()
  })

  async function seedRun(
    options: {
      readonly status?: RunStatus
      readonly deadline?: Date | null
      readonly parentRunId?: string | null
      readonly conversationId?: string
    } = {},
  ): Promise<{ readonly run: StoredRun; readonly id: string; readonly conversationId: string }> {
    const conversationId = options.conversationId ?? crypto.randomUUID()
    await store.createConversationWithUserMessage({
      conversationId,
      messageId: crypto.randomUUID(),
      subject: "owner-contract",
      content: { text: "seed" },
      triggerSource: "channel",
      idempotencyKey: crypto.randomUUID(),
      createdAt: BASE_AT,
    })
    let run = await store.createRun({
      id: crypto.randomUUID(),
      conversationId,
      parentRunId: options.parentRunId ?? null,
      triggerSource: options.parentRunId ? "parent_run" : "channel",
      idempotencyKey: crypto.randomUUID(),
      subject: "owner-contract",
      goal: "contract",
      budget: { maxSteps: 5 },
      deadline: options.deadline ?? null,
      createdAt: BASE_AT,
    })
    const path = PATH_TO[options.status ?? "queued"]
    for (const [index, status] of path.entries()) {
      run = await store.transitionRunStatus(run.id, run.version, status, at(index + 1))
    }
    return { run, id: run.id, conversationId }
  }

  it("accepts the full legal transition matrix", () => {
    for (const [from, to] of LEGAL_EDGES) {
      const label = `${from} -> ${to}`
      expect(canTransitionRun(from, to), label).toBe(true)
      const result = transitionRun(makeDomainRun(from), to, 42)
      expect(result._tag, label).toBe("TransitionAccepted")
      if (result._tag === "TransitionAccepted") {
        expect(result.run.status, label).toBe(to)
        expect(result.run.version, label).toBe(2)
      }
    }
  })

  it("rejects the full illegal transition matrix", () => {
    for (const [from, to] of ILLEGAL_EDGES) {
      const label = `${from} -> ${to}`
      expect(canTransitionRun(from, to), label).toBe(false)
      const result = transitionRun(makeDomainRun(from), to, 42)
      expect(result._tag, label).toBe("TransitionRejected")
      if (result._tag === "TransitionRejected") {
        expect(result.from, label).toBe(from)
        expect(result.to, label).toBe(to)
        // 被拒后原 Run 不可被改写。
        expect(result.run.status, label).toBe(from)
        expect(result.run.version, label).toBe(1)
      }
    }
  })

  it("persists a legal multi-hop chain and shows it back through the store", async () => {
    const { id } = await seedRun({ status: "queued" })
    const hops: RunStatus[] = ["running", "waiting_approval", "running", "succeeded"]
    let expectedVersion = 1
    for (const [index, status] of hops.entries()) {
      const current = await store.getRun(id)
      expect(current).not.toBeNull()
      if (!current) return
      const next = await store.transitionRunStatus(
        current.id,
        current.version,
        status,
        at(index + 1),
      )
      expect(next.status).toBe(status)
      expect(next.version).toBe(expectedVersion + 1)
      expectedVersion += 1
    }
    expect((await store.getRun(id))?.status).toBe("succeeded")
  })

  it.each(TERMINAL_RUN_STATUSES)("treats %s as a dead end", async (terminal) => {
    expect(isTerminalRunStatus(terminal)).toBe(true)
    const { id } = await seedRun({ status: terminal })

    await expect(cancelRun(store, id, { subject: "owner-contract" })).rejects.toBeInstanceOf(
      IllegalRunTransitionError,
    )
    await expect(expireRun(store, id, { force: true, now: BASE_AT })).rejects.toBeInstanceOf(
      IllegalRunTransitionError,
    )
    const completed = await transitionRunToTerminal(store, id, {
      from: ["queued", "running", "waiting_approval", "waiting_external"],
      to: "succeeded",
      now: BASE_AT,
    })
    expect(completed).toBeNull()
    expect((await store.getRun(id))?.status).toBe(terminal)
  })

  it("does not complete a Run twice through transitionRunToTerminal", async () => {
    const { id } = await seedRun({ status: "running" })
    const first = await transitionRunToTerminal(store, id, {
      from: ["running"],
      to: "succeeded",
      now: at(1),
    })
    expect(first?.status).toBe("succeeded")
    const second = await transitionRunToTerminal(store, id, {
      from: ["running"],
      to: "succeeded",
      now: at(2),
    })
    expect(second).toBeNull()
    const stored = await store.getRun(id)
    expect(stored?.status).toBe("succeeded")
    expect(stored?.version).toBe(first?.version)
  })

  it("throws RuntimeVersionConflictError on a stale optimistic write", async () => {
    const { id, run } = await seedRun({ status: "running" })
    const won = await store.transitionRunStatus(id, run.version, "cancelled", at(1))
    expect(won.status).toBe("cancelled")

    await expect(
      store.transitionRunStatus(id, run.version, "failed", at(2)),
    ).rejects.toBeInstanceOf(RuntimeVersionConflictError)
    const stored = await store.getRun(id)
    expect(stored?.status).toBe("cancelled")
    expect(stored?.version).toBe(run.version + 1)
  })

  it("expireRun refuses runs with no deadline or an unreached deadline, unless forced", async () => {
    const noDeadline = await seedRun({ status: "running", deadline: null })
    await expect(expireRun(store, noDeadline.id, { now: BASE_AT })).rejects.toThrow(/no deadline/)
    const forced = await expireRun(store, noDeadline.id, { now: BASE_AT, force: true })
    expect(forced.status).toBe("expired")

    const future = await seedRun({ status: "running", deadline: at(3600) })
    await expect(expireRun(store, future.id, { now: BASE_AT })).rejects.toThrow(
      /deadline not reached/,
    )
    expect((await store.getRun(future.id))?.status).toBe("running")
    expect((await expireRun(store, future.id, { now: BASE_AT, force: true })).status).toBe(
      "expired",
    )
  })

  it("sweeps only active runs whose deadline has passed", async () => {
    const overdue = await seedRun({ status: "running", deadline: at(-60) })
    const future = await seedRun({ status: "running", deadline: at(3600) })
    const alreadyDone = await seedRun({ status: "succeeded", deadline: at(-120) })

    const swept = await expireOverdueRuns(store, { now: BASE_AT })
    expect(swept.map((run) => run.id)).toEqual([overdue.id])
    expect((await store.getRun(overdue.id))?.status).toBe("expired")
    expect((await store.getRun(future.id))?.status).toBe("running")
    expect((await store.getRun(alreadyDone.id))?.status).toBe("succeeded")

    // 重复清扫是幂等的：已经终态的行不会被再次计数。
    expect(await expireOverdueRuns(store, { now: BASE_AT })).toHaveLength(0)
  })

  it("cancels descendants recursively and leaves terminal descendants untouched", async () => {
    const root = await seedRun({ status: "running" })
    const child = await seedRun({
      status: "waiting_approval",
      parentRunId: root.id,
      conversationId: root.conversationId,
    })
    const grandchild = await seedRun({
      status: "running",
      parentRunId: child.id,
      conversationId: root.conversationId,
    })
    const finishedChild = await seedRun({
      status: "succeeded",
      parentRunId: root.id,
      conversationId: root.conversationId,
    })

    const cancelled = await cancelRunCascade(store, root.id, { subject: "owner-contract" })
    expect(cancelled.map((run) => run.id).sort()).toEqual([root.id, child.id, grandchild.id].sort())
    expect(cancelled.every((run) => run.status === "cancelled")).toBe(true)
    expect((await store.getRun(root.id))?.status).toBe("cancelled")
    expect((await store.getRun(child.id))?.status).toBe("cancelled")
    expect((await store.getRun(grandchild.id))?.status).toBe("cancelled")
    expect((await store.getRun(finishedChild.id))?.status).toBe("succeeded")
    expect(await cancelRunCascade(store, root.id, { subject: "owner-contract" })).toHaveLength(0)
  })
})

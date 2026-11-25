import { describe, expect, it, vi } from "vitest"
import type { TraceEvent } from "@butler/domain/observability/local-trace.js"
import { createTraceEvent } from "@butler/domain/observability/local-trace.js"
import {
  createRuntimeStore,
  createTaskStore,
  createTraceStore,
  type RuntimeStore,
  type TaskStore,
} from "@butler/persistence"
import { makeTestDb } from "@butler/persistence/testing.js"
import { createTaskRecord } from "@butler/domain/knowledge/task-procedure.js"
import type { Wiring } from "./wiring.js"
import {
  collectWeeklyDigest,
  hasWeeklyDigestSentForDay,
  renderEmptyWeeklyDigest,
  renderWeeklyDigest,
  WEEKLY_DIGEST_WINDOW_MS,
} from "./weekly-digest.js"
import {
  isWithinWeeklyDigestWindow,
  runWeeklyDigestTick,
  type WeeklyDigestConfig,
} from "./weekly-digest-worker.js"
import { parseWeeklyDigestConfig } from "./weekly-digest-config.js"
import { tryWechatWeeklyDigestCommand } from "./wechat-weekly-digest-command.js"

const DAY_MS = 24 * 60 * 60 * 1000
/** 2026-11-23 09:00 Asia/Shanghai. */
const NOW = Date.UTC(2026, 10, 23, 1, 0, 0)
const SUBJECT = "u-owner"

function weekdayOf(ms: number): number {
  return new Date(ms + 8 * 60 * 60 * 1000).getUTCDay()
}

/**
 * `listRecentAuditEvents` anchors its window to the real clock, so a fixed
 * window breaks as soon as wall time drifts past it. Compute the window
 * relative to `NOW` instead: cutoff becomes `NOW - DAY_MS` regardless of
 * today's date.
 */
function auditWindowAroundNow(): number {
  return Date.now() - NOW + DAY_MS
}

function baseConfig(overrides: Partial<WeeklyDigestConfig> = {}): WeeklyDigestConfig {
  return {
    enabled: true,
    to: SUBJECT,
    weekday: weekdayOf(NOW),
    hour: 9,
    minute: 0,
    tickMs: 60_000,
    ...overrides,
  }
}

function failedRunEvent(createdAt: number): TraceEvent {
  return { kind: "step", name: "run_failed", createdAt } as unknown as TraceEvent
}

async function setup() {
  const db = await makeTestDb()
  const taskStore = createTaskStore(db.db)
  const runtimeStore = createRuntimeStore(db.db)
  const wiring = {
    taskStore,
    runtimeStore,
    channels: new Map(),
  } as unknown as Wiring
  return { db, taskStore, runtimeStore, wiring }
}

async function addTask(
  store: TaskStore,
  input: { title: string; status: "open" | "done"; nowMs: number },
): Promise<void> {
  const created = createTaskRecord({
    subject: SUBJECT,
    title: input.title,
    goal: input.title,
    status: input.status,
    nowMs: input.nowMs,
  })
  if (!created.ok) throw new Error(created.reason)
  await store.create(created.value)
}

async function addApprovalAudit(store: RuntimeStore, createdAt: number): Promise<void> {
  await store.appendAuditEvent({
    auditId: crypto.randomUUID(),
    runId: null,
    conversationId: null,
    action: "approval.requested",
    subject: SUBJECT,
    detail: {},
    createdAt: new Date(createdAt),
    actor: "owner-direct",
  })
}

describe("collectWeeklyDigest", () => {
  it("counts completed / open tasks, failed runs and approvals in the window", async () => {
    const { db, taskStore, runtimeStore, wiring } = await setup()
    try {
      await addTask(taskStore, { title: "本周完成", status: "done", nowMs: NOW - DAY_MS })
      await addTask(taskStore, { title: "上周完成", status: "done", nowMs: NOW - 8 * DAY_MS })
      await addTask(taskStore, { title: "待办", status: "open", nowMs: NOW - 2 * DAY_MS })
      await addApprovalAudit(runtimeStore, NOW - DAY_MS)
      await addApprovalAudit(runtimeStore, NOW - 9 * DAY_MS)

      const data = await collectWeeklyDigest({
        wiring,
        subject: SUBJECT,
        nowMs: NOW,
        tracer: {
          list: () => [failedRunEvent(NOW - 2 * DAY_MS), failedRunEvent(NOW - 9 * DAY_MS)],
        },
      })

      expect(data).toMatchObject({
        completedTasks: 1,
        openTasks: 1,
        failedRuns: 1,
        approvals: 1,
        windowStartMs: NOW - WEEKLY_DIGEST_WINDOW_MS,
        windowEndMs: NOW,
        hasData: true,
      })
    } finally {
      await db.close()
    }
  })

  it("counts failed runs from the persisted trace store, not the memory buffer", async () => {
    const { db, wiring } = await setup()
    try {
      const traceStore = createTraceStore(db.db)
      await traceStore.append([
        createTraceEvent({ kind: "step", name: "run_failed", nowMs: NOW - DAY_MS }),
        // Real emitter shape (run-engine): a failed run is `run/finish`+error.
        createTraceEvent({
          kind: "run",
          name: "finish",
          status: "error",
          nowMs: NOW - 2 * 60 * 60 * 1000,
        }),
        createTraceEvent({ kind: "step", name: "run_failed", nowMs: NOW - 9 * DAY_MS }),
      ])
      const data = await collectWeeklyDigest({
        wiring: { ...wiring, traceStore } as unknown as Wiring,
        subject: SUBJECT,
        nowMs: NOW,
        // Empty memory buffer proves the persisted path is the source.
        tracer: { list: () => [] },
      })
      expect(data.failedRuns).toBe(2)
    } finally {
      await db.close()
    }
  })

  it("marks an empty week when every counter is zero", async () => {
    const { db, wiring } = await setup()
    try {
      const data = await collectWeeklyDigest({
        wiring,
        subject: SUBJECT,
        nowMs: NOW,
        tracer: { list: () => [] },
      })
      expect(data.hasData).toBe(false)
      expect(data.completedTasks + data.openTasks + data.failedRuns + data.approvals).toBe(0)
    } finally {
      await db.close()
    }
  })

  it("fails clearly when the task store is unavailable", async () => {
    const { db, runtimeStore } = await setup()
    try {
      const wiring = { taskStore: null, runtimeStore, channels: new Map() } as unknown as Wiring
      await expect(
        collectWeeklyDigest({
          wiring,
          subject: SUBJECT,
          nowMs: NOW,
          tracer: { list: () => [] },
        }),
      ).rejects.toThrow("任务存储暂不可用")
    } finally {
      await db.close()
    }
  })
})

describe("weekly digest rendering", () => {
  const data = {
    completedTasks: 3,
    openTasks: 5,
    failedRuns: 1,
    approvals: 2,
    windowStartMs: NOW - WEEKLY_DIGEST_WINDOW_MS,
    windowEndMs: NOW,
    hasData: true,
  }

  it("renders the four numbers in a stable structure", () => {
    expect(renderWeeklyDigest(data)).toBe(
      ["【周报】11-16 ~ 11-23", "完成 3 项", "待办 5 项", "失败 1 次", "审批 2 次"].join("\n"),
    )
  })

  it("renders a quiet-week message without numbers", () => {
    expect(renderEmptyWeeklyDigest({ ...data, hasData: false })).toContain("没有可汇总的记录")
  })
})

describe("weekly digest config", () => {
  it("defaults to disabled, Monday 09:00, 60s tick", () => {
    expect(parseWeeklyDigestConfig({})).toEqual({
      enabled: false,
      to: null,
      weekday: 1,
      hour: 9,
      minute: 0,
      tickMs: 60_000,
    })
  })

  it("parses enabled / recipient / weekday / time", () => {
    expect(
      parseWeeklyDigestConfig({
        BUTLER_V5_WEEKLY_DIGEST_ENABLED: "1",
        BUTLER_V5_WEEKLY_DIGEST_TO: " u-owner ",
        BUTLER_V5_WEEKLY_DIGEST_WEEKDAY: "5",
        BUTLER_V5_WEEKLY_DIGEST_TIME: "18:30",
      }),
    ).toMatchObject({ enabled: true, to: "u-owner", weekday: 5, hour: 18, minute: 30 })
  })

  it("falls back on invalid time / weekday / tick", () => {
    expect(
      parseWeeklyDigestConfig({
        BUTLER_V5_WEEKLY_DIGEST_TIME: "25:99",
        BUTLER_V5_WEEKLY_DIGEST_WEEKDAY: "9",
        BUTLER_V5_WEEKLY_DIGEST_TICK_MS: "1",
      }),
    ).toMatchObject({ hour: 9, minute: 0, weekday: 6, tickMs: 5_000 })
  })
})

describe("runWeeklyDigestTick", () => {
  it("stays quiet when disabled or without a recipient", async () => {
    const { db, wiring } = await setup()
    try {
      expect(await runWeeklyDigestTick({ wiring, config: baseConfig({ enabled: false }) })).toEqual(
        {
          sent: false,
          reason: "disabled",
        },
      )
      expect(await runWeeklyDigestTick({ wiring, config: baseConfig({ to: null }) })).toEqual({
        sent: false,
        reason: "no_owner",
      })
    } finally {
      await db.close()
    }
  })

  it("only fires on the configured weekday and time window", async () => {
    const { db, wiring } = await setup()
    try {
      const wrongDay = baseConfig({ weekday: (weekdayOf(NOW) + 1) % 7 })
      expect(isWithinWeeklyDigestWindow(wrongDay, NOW)).toBe(false)
      expect(await runWeeklyDigestTick({ wiring, config: wrongDay, nowMs: () => NOW })).toEqual({
        sent: false,
        reason: "not_scheduled",
      })

      const later = NOW + 11 * 60_000
      expect(isWithinWeeklyDigestWindow(baseConfig(), later)).toBe(false)
    } finally {
      await db.close()
    }
  })

  it("does not send on an empty week", async () => {
    const { db, wiring } = await setup()
    try {
      const send = vi.fn(async () => ({ ok: true as const }))
      const result = await runWeeklyDigestTick({
        wiring,
        config: baseConfig(),
        nowMs: () => NOW,
        tracer: { list: () => [] },
        send,
      })
      expect(result).toEqual({ sent: false, reason: "empty" })
      expect(send).not.toHaveBeenCalled()
    } finally {
      await db.close()
    }
  })

  it("sends once, records audit and dedupes the same day", async () => {
    const { db, taskStore, wiring } = await setup()
    try {
      await addTask(taskStore, { title: "本周完成", status: "done", nowMs: NOW - DAY_MS })
      const send = vi.fn(async () => ({ ok: true as const }))

      const first = await runWeeklyDigestTick({
        wiring,
        config: baseConfig(),
        nowMs: () => NOW,
        tracer: { list: () => [] },
        send,
      })
      expect(first.sent).toBe(true)
      if (!first.sent) throw new Error("expected send")
      expect(first.text).toContain("完成 1 项")
      expect(send).toHaveBeenCalledTimes(1)
      expect(
        await hasWeeklyDigestSentForDay({
          wiring,
          subject: SUBJECT,
          dayKey: "2026-11-23",
        }),
      ).toBe(true)

      const second = await runWeeklyDigestTick({
        wiring,
        config: baseConfig(),
        nowMs: () => NOW,
        tracer: { list: () => [] },
        send,
      })
      expect(second).toEqual({ sent: false, reason: "already_sent" })
      expect(send).toHaveBeenCalledTimes(1)
    } finally {
      await db.close()
    }
  })

  it("records a failed audit when the send fails", async () => {
    const { db, taskStore, runtimeStore, wiring } = await setup()
    try {
      await addTask(taskStore, { title: "本周完成", status: "done", nowMs: NOW - DAY_MS })
      const result = await runWeeklyDigestTick({
        wiring,
        config: baseConfig(),
        nowMs: () => NOW,
        tracer: { list: () => [] },
        send: async () => ({ ok: false, reason: "network" }),
      })
      expect(result).toEqual({ sent: false, reason: "send_failed", text: expect.any(String) })
      const audits = await runtimeStore.listRecentAuditEvents({
        windowMs: auditWindowAroundNow(),
        limit: 10,
      })
      expect(audits.some((e) => e.action === "weekly_digest.failed")).toBe(true)
    } finally {
      await db.close()
    }
  })

  it("records a failed audit when collection throws", async () => {
    const { db, runtimeStore } = await setup()
    try {
      const wiring = {
        taskStore: {
          listBySubject: async () => {
            throw new Error("db down")
          },
        },
        runtimeStore,
        channels: new Map(),
      } as unknown as Wiring
      const result = await runWeeklyDigestTick({
        wiring,
        config: baseConfig(),
        nowMs: () => NOW,
        tracer: { list: () => [] },
        send: async () => ({ ok: true }),
      })
      expect(result).toEqual({ sent: false, reason: "error", text: "周报生成失败：db down" })
      const audits = await runtimeStore.listRecentAuditEvents({
        windowMs: auditWindowAroundNow(),
        limit: 10,
      })
      expect(audits.some((e) => e.action === "weekly_digest.failed")).toBe(true)
    } finally {
      await db.close()
    }
  })
})

describe("tryWechatWeeklyDigestCommand", () => {
  function commandWiring(overrides: {
    tasks?: Awaited<ReturnType<TaskStore["listBySubject"]>>
    failTaskStore?: boolean
  }): { wiring: Wiring; audits: unknown[] } {
    const audits: unknown[] = []
    const wiring = {
      taskStore: {
        listBySubject: async () => {
          if (overrides.failTaskStore) throw new Error("db down")
          return overrides.tasks ?? []
        },
      },
      runtimeStore: {
        listRecentAuditEvents: async () => [],
        appendAuditEvent: async (event: unknown) => {
          audits.push(event)
        },
      },
      channels: new Map(),
    } as unknown as Wiring
    return { wiring, audits }
  }

  it("ignores other content", async () => {
    const { wiring } = commandWiring({})
    expect(
      await tryWechatWeeklyDigestCommand({
        wiring,
        fromUserId: SUBJECT,
        content: "/待办",
        nowMs: () => NOW,
      }),
    ).toBeNull()
  })

  it("returns the same structure as the scheduled push", async () => {
    const task = createTaskRecord({
      subject: SUBJECT,
      title: "本周完成",
      goal: "本周完成",
      status: "done",
      nowMs: NOW - DAY_MS,
    })
    if (!task.ok) throw new Error(task.reason)
    const { wiring } = commandWiring({ tasks: [task.value] })
    const result = await tryWechatWeeklyDigestCommand({
      wiring,
      fromUserId: SUBJECT,
      content: "/周报",
      nowMs: () => NOW,
      tracer: { list: () => [] },
    })
    expect(result?.reply).toContain("完成 1 项")
    expect(result?.reply).toContain("待办 0 项")
    expect(result?.reply).toContain("失败 0 次")
    expect(result?.reply).toContain("审批 0 次")
  })

  it("reports an empty week without failing", async () => {
    const { wiring } = commandWiring({})
    const result = await tryWechatWeeklyDigestCommand({
      wiring,
      fromUserId: SUBJECT,
      content: "/weekly",
      nowMs: () => NOW,
      tracer: { list: () => [] },
    })
    expect(result?.reply).toContain("没有可汇总的记录")
  })

  it("returns an owner-facing failure and audits it", async () => {
    const { wiring, audits } = commandWiring({ failTaskStore: true })
    const result = await tryWechatWeeklyDigestCommand({
      wiring,
      fromUserId: SUBJECT,
      content: "/周报",
      nowMs: () => NOW,
      tracer: { list: () => [] },
    })
    expect(result?.reply).toBe("周报生成失败：db down")
    expect(audits).toHaveLength(1)
  })
})

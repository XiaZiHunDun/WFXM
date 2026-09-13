import { randomUUID } from "node:crypto"
import { mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { makeTestDb } from "@butler/persistence/testing.js"
import { EventBridge } from "@butler/persistence/event-bridge.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { createProjectKnowledgeStore, createTaskStore, type TaskRecord, type TaskStore } from "@butler/persistence"
import { makeWiring, type Wiring } from "./wiring.js"
import { setWechatActiveProjectId } from "./wechat-active-project.js"
import type * as TaskRunBackgroundModule from "./task-run-background.js"
import { tryWechatTaskCommand } from "./wechat-task-commands.js"

// Stub the background-task-runner so async /运行 is exercised without a real LLM loop.
// Sync /运行 is also stubbed via the same module boundary.
vi.mock("./task-run-background.js", async () => {
  const actual = await vi.importActual<typeof TaskRunBackgroundModule>(
    "./task-run-background.js",
  )
  return {
    ...actual,
    scheduleBackgroundTaskRun: vi.fn(() => ({ ok: true })),
  }
})
vi.mock("./task-run.js", async () => {
  return {
    runTaskGoal: vi.fn(async () => ({
      loop: {
        reply: "ran OK",
        iterations: 1,
        toolCalls: 0,
        finalDecision: "Finish" as const,
        traces: ["stub:run"],
      },
    })),
  }
})

import { scheduleBackgroundTaskRun } from "./task-run-background.js"
import { runTaskGoal } from "./task-run.js"

const mockedSchedule = vi.mocked(scheduleBackgroundTaskRun)
const mockedRunTaskGoal = vi.mocked(runTaskGoal)

describe("tryWechatTaskCommand", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let wiring: Wiring
  let taskStore: TaskStore
  let storeDir = ""
  let env: NodeJS.ProcessEnv

  beforeEach(async () => {
    db = await makeTestDb()
    const bridge = new EventBridge({ db: db.db, workerId: "task-cmd-test" })
    const ts = createTaskStore(db.db)
    wiring = makeWiring({
      bridge,
      workerId: "task-cmd-test",
      runtimeStore: createRuntimeStore(db.db),
      runEngine: new RunEngine(createRuntimeStore(db.db)),
      db: db.db,
      backfillConversation: async () => undefined,
      projectKnowledgeStore: createProjectKnowledgeStore(db.db),
      taskStore: ts,
    })
    if (!wiring.taskStore) throw new Error("test wiring must wire taskStore")
    taskStore = wiring.taskStore
    storeDir = mkdtempSync(join(tmpdir(), "butler-task-cmd-"))
    env = {
      BUTLER_V5_WECHAT_ACTIVE_PROJECT_STORE: join(storeDir, "active.json"),
      BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH: join(process.cwd(), "config/wechat-tool-allowlist.json"),
      BUTLER_V5_WECHAT_PROJECT_PATHS: join(process.cwd(), "config/wechat-project-paths.json"),
      BUTLER_V5_WORKSPACE_ROOT: join(process.cwd(), ".."),
      BUTLER_V5_TASK_RUN_ASYNC: "0",
      BUTLER_V5_RUN_NOTIFY_ENABLED: "0",
    }
    // Pin every distinct test user to WFXM so titles use [WFXM] prefix.
    for (const u of [
      "u-routing",
      "u-no-store",
      "u-list",
      "u-empty",
      "u-alias-a",
      "u-alias-b",
      "u-add",
      "u-pipe",
      "u-new",
      "u-run-sync",
      "u-run-usage",
      "u-run-404",
      "u-run-short",
      "u-run-async",
      "u-run-busy",
      "u-run-err",
      "u-done",
      "u-done-usage",
      "u-done-404",
      "u-done-race",
    ]) {
      setWechatActiveProjectId(u, "WFXM", env)
    }
    mockedSchedule.mockClear()
    mockedRunTaskGoal.mockClear()
    // Default: async scheduler returns ok=true unless a test overrides.
    mockedSchedule.mockReturnValue({ ok: true })
  })

  afterEach(async () => {
    await db.close()
    if (storeDir) rmSync(storeDir, { recursive: true, force: true })
  })

  // ─── routing guard ──────────────────────────────────────────────────────
  it("returns null when content does not match any task slash command", async () => {
    const result = await tryWechatTaskCommand({
      wiring,
      fromUserId: "u-routing",
      content: "/记忆 hello",
      env,
    })
    expect(result).toBeNull()
  })

  // ─── no-store branch ────────────────────────────────────────────────────
  it("returns 'Task 存储不可用。' when wiring.taskStore is null", async () => {
    const noStoreWiring: Wiring = { ...wiring, taskStore: null }
    const result = await tryWechatTaskCommand({
      wiring: noStoreWiring,
      fromUserId: "u-no-store",
      content: "/待办",
      env,
    })
    expect(result?.reply).toBe("Task 存储不可用。")
    expect(result?.traces).toContain("wechat-task: no store")
  })

  // ─── /待办 (list) ───────────────────────────────────────────────────────
  it("/待办 lists open tasks scoped to active project", async () => {
    // Seed two open tasks in two different projects + one done.
    const t1 = await taskStore.create({
      id: randomUUID(),
      subject: "u-list",
      title: "[WFXM] do thing one",
      goal: "goal one",
      status: "open",
      conversationId: null,
      procedureId: null,
      procedureStepIndex: null,
      createdAt: 0,
      updatedAt: 0,
    } satisfies TaskRecord)
    await taskStore.create({
      id: randomUUID(),
      subject: "u-list",
      title: "[other] hidden task",
      goal: "g",
      status: "open",
      conversationId: null,
      procedureId: null,
      procedureStepIndex: null,
      createdAt: 0,
      updatedAt: 0,
    })
    await taskStore.create({
      id: randomUUID(),
      subject: "u-list",
      title: "[WFXM] completed thing",
      goal: "g",
      status: "done",
      conversationId: null,
      procedureId: null,
      procedureStepIndex: null,
      createdAt: 0,
      updatedAt: 0,
    })

    const result = await tryWechatTaskCommand({
      wiring,
      fromUserId: "u-list",
      content: "/待办",
      env,
    })
    expect(result).not.toBeNull()
    if (!result) throw new Error("/待办 should return non-null result")
    expect(result.reply).toContain("待办（WFXM）")
    expect(result.reply).toContain("do thing one")
    expect(result.reply).toContain(t1.id.slice(0, 8))
    expect(result.reply).not.toContain("hidden task")
    expect(result.reply).not.toContain("completed thing")
    expect(result.reply).toContain("/运行 <id>")
    expect(result.reply).toContain("/完成 <id>")
  })

  it("/待办 (empty) returns the digest emptyMessage; no items shown", async () => {
    const result = await tryWechatTaskCommand({
      wiring,
      fromUserId: "u-empty",
      content: "/待办",
      env,
    })
    expect(result?.reply).toContain("没有 open 待办")
    expect(result?.reply).toContain("/待办 新增 <标题>")
    expect(result?.traces).toContain("wechat-task: empty list")
  })

  it("/tasks alias: routing guard rejects before alias match can fire (documented behavior)", async () => {
    // The routing guard at line 98 returns null for anything that does not
    // startsWith("/待办" | "/运行" | "/完成"). The /tasks equality-alias at
    // line 110 is therefore unreachable in current routing. This test pins
    // that behavior so future guard changes are intentional (D56 audit F3).
    const a = await tryWechatTaskCommand({
      wiring,
      fromUserId: "u-alias-a",
      content: "/待办",
      env,
    })
    expect(a).not.toBeNull()
    expect(a?.reply).toContain("没有 open 待办")
    const b = await tryWechatTaskCommand({
      wiring,
      fromUserId: "u-alias-a",
      content: "/tasks",
      env,
    })
    // /tasks hits the routing-guard null branch — caller must fall through.
    expect(b).toBeNull()
  })

  // ─── /待办 新增 / 新建 ──────────────────────────────────────────────────
  it("/待办 新增 <title> creates an open task scoped to active project", async () => {
    const result = await tryWechatTaskCommand({
      wiring,
      fromUserId: "u-add",
      content: "/待办 新增 写周报",
      env,
    })
    expect(result?.reply).toMatch(/^已添加待办 [0-9a-f]{8}：写周报/)
    expect(result?.reply).toContain("/运行")
    expect(result?.traces.some((t) => t.startsWith("wechat-task: created "))).toBe(true)

    const stored = await taskStore.listBySubject({ subject: "u-add" })
    expect(stored).toHaveLength(1)
    expect(stored[0].title).toBe("[WFXM] 写周报")
    expect(stored[0].goal).toBe("写周报")
    expect(stored[0].status).toBe("open")
  })

  it("/待办 新增 <title> | <goal> separates title and goal", async () => {
    const result = await tryWechatTaskCommand({
      wiring,
      fromUserId: "u-pipe",
      content: "/待办 新增 完成 D56 | 写测试 + 改 runtime-store 事务",
      env,
    })
    expect(result?.reply).toContain("完成 D56")
    const stored = await taskStore.listBySubject({ subject: "u-pipe" })
    expect(stored[0].title).toBe("[WFXM] 完成 D56")
    expect(stored[0].goal).toBe("写测试 + 改 runtime-store 事务")
  })

  it("/待办 新增 with empty content returns usage", async () => {
    const r1 = await tryWechatTaskCommand({
      wiring,
      fromUserId: "u-empty",
      content: "/待办 新增",
      env,
    })
    const r2 = await tryWechatTaskCommand({
      wiring,
      fromUserId: "u-empty",
      content: "/待办 新增 ",
      env,
    })
    expect(r1?.reply).toBe("用法：/待办 新增 <标题> [| <目标>]")
    expect(r2?.reply).toBe("用法：/待办 新增 <标题> [| <目标>]")
    expect(r1?.traces).toContain("wechat-task: add usage")
  })

  it("/待办 新建 is an alias of /待办 新增", async () => {
    const result = await tryWechatTaskCommand({
      wiring,
      fromUserId: "u-new",
      content: "/待办 新建 起草 design doc",
      env,
    })
    expect(result?.reply).toMatch(/已添加待办 [0-9a-f]{8}：起草 design doc/)
    const stored = await taskStore.listBySubject({ subject: "u-new" })
    expect(stored).toHaveLength(1)
    expect(stored[0].title).toBe("[WFXM] 起草 design doc")
  })

  // ─── /运行 sync ─────────────────────────────────────────────────────────
  it("/运行 (sync mode) calls runTaskGoal and returns loop result", async () => {
    const task = await taskStore.create({
      id: randomUUID(),
      subject: "u-run-sync",
      title: "[WFXM] do sync work",
      goal: "g",
      status: "open",
      conversationId: null,
      procedureId: null,
      procedureStepIndex: null,
      createdAt: 0,
      updatedAt: 0,
    })
    mockedRunTaskGoal.mockClear()
    const result = await tryWechatTaskCommand({
      wiring,
      fromUserId: "u-run-sync",
      content: `/运行 ${task.id}`,
      env,
    })
    expect(mockedRunTaskGoal).toHaveBeenCalledTimes(1)
    expect(result?.reply).toContain(`待办 ${task.id.slice(0, 8)} 已运行。`)
    expect(result?.reply).toContain("ran OK")
    expect(result?.finalDecision).toBe("Finish")
    expect(result?.traces.some((t) => t.startsWith("wechat-task: run "))).toBe(true)
    expect(mockedSchedule).not.toHaveBeenCalled()
  })

  it("/运行 with no token returns usage", async () => {
    const result = await tryWechatTaskCommand({
      wiring,
      fromUserId: "u-run-usage",
      content: "/运行",
      env,
    })
    expect(result?.reply).toBe("用法：/运行 <待办id前缀>")
    expect(result?.traces).toContain("wechat-task: run usage")
  })

  it("/运行 with unknown token returns not-found reply", async () => {
    const result = await tryWechatTaskCommand({
      wiring,
      fromUserId: "u-run-404",
      content: "/运行 deadbeef",
      env,
    })
    expect(result?.reply).toContain("未找到待办「deadbeef」")
    expect(result?.traces).toContain("wechat-task: run not found")
    expect(mockedRunTaskGoal).not.toHaveBeenCalled()
  })

  it("/运行 accepts short 8-char id prefix", async () => {
    const task = await taskStore.create({
      id: randomUUID(),
      subject: "u-run-short",
      title: "[WFXM] by short id",
      goal: "g",
      status: "open",
      conversationId: null,
      procedureId: null,
      procedureStepIndex: null,
      createdAt: 0,
      updatedAt: 0,
    })
    const result = await tryWechatTaskCommand({
      wiring,
      fromUserId: "u-run-short",
      content: `/运行 ${task.id.slice(0, 8)}`,
      env,
    })
    expect(result?.reply).toContain("已运行")
    expect(mockedRunTaskGoal.mock.calls[0]?.[0].taskId).toBe(task.id)
  })

  it("/运行 (async mode) delegates to scheduler; sync runTaskGoal NOT called", async () => {
    const task = await taskStore.create({
      id: randomUUID(),
      subject: "u-run-async",
      title: "[WFXM] async work",
      goal: "g",
      status: "open",
      conversationId: null,
      procedureId: null,
      procedureStepIndex: null,
      createdAt: 0,
      updatedAt: 0,
    })
    mockedRunTaskGoal.mockClear()
    mockedSchedule.mockClear()
    const asyncEnv = { ...env, BUTLER_V5_TASK_RUN_ASYNC: "1", BUTLER_V5_RUN_NOTIFY_ENABLED: "1" }
    const result = await tryWechatTaskCommand({
      wiring,
      fromUserId: "u-run-async",
      content: `/运行 ${task.id}`,
      env: asyncEnv,
    })
    expect(mockedSchedule).toHaveBeenCalledTimes(1)
    expect(mockedRunTaskGoal).not.toHaveBeenCalled()
    expect(result?.reply).toContain("已在后台运行")
    // D60 T2.3 (audit #3 F-07): env-var knobs removed from owner reply.
    expect(result?.reply).not.toMatch(/BUTLER_V5_/)
    expect(result?.traces.some((t) => t.startsWith("wechat-task: async run "))).toBe(true)
  })

  it("/运行 (async mode) surfaces busy reason when scheduler rejects", async () => {
    const task = await taskStore.create({
      id: randomUUID(),
      subject: "u-run-busy",
      title: "[WFXM] busy",
      goal: "g",
      status: "open",
      conversationId: null,
      procedureId: null,
      procedureStepIndex: null,
      createdAt: 0,
      updatedAt: 0,
    })
    mockedSchedule.mockReturnValue({ ok: false, reason: "运行中" })
    const asyncEnv = { ...env, BUTLER_V5_TASK_RUN_ASYNC: "1" }
    const result = await tryWechatTaskCommand({
      wiring,
      fromUserId: "u-run-busy",
      content: `/运行 ${task.id}`,
      env: asyncEnv,
    })
    expect(result?.reply).toBe("运行中")
    expect(result?.traces.some((t) => t.startsWith("wechat-task: run busy "))).toBe(true)
  })

  it("/运行 (sync mode) catches runTaskGoal throw and surfaces message", async () => {
    const task = await taskStore.create({
      id: randomUUID(),
      subject: "u-run-err",
      title: "[WFXM] err",
      goal: "g",
      status: "open",
      conversationId: null,
      procedureId: null,
      procedureStepIndex: null,
      createdAt: 0,
      updatedAt: 0,
    })
    mockedRunTaskGoal.mockRejectedValueOnce(new Error("loop blew up"))
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {})
    try {
      const result = await tryWechatTaskCommand({
        wiring,
        fromUserId: "u-run-err",
        content: `/运行 ${task.id}`,
        env,
      })
      // D61 T1: owner sees Chinese fallback (NOT the raw err.message leak).
      expect(result?.reply).toContain("运行失败，请稍后重试")
      expect(result?.reply).not.toContain("loop blew up")
      // Operator log preserves full error for grep-ability.
      const logCall = errorSpy.mock.calls.find(
        (c) => Array.isArray(c) && c[0] === "[safe-owner-error]",
      )
      expect(logCall).toBeDefined()
      const payload = logCall?.[1] as { message?: string } | undefined
      expect(payload?.message).toBe("loop blew up")
      expect(result?.traces.some((t) => t.startsWith("wechat-task: run error "))).toBe(true)
    } finally {
      errorSpy.mockRestore()
    }
  })

  // ─── /完成 ──────────────────────────────────────────────────────────────
  it("/完成 <id> shows confirm gate when no confirm suffix", async () => {
    const task = await taskStore.create({
      id: randomUUID(),
      subject: "u-done",
      title: "[WFXM] to finish",
      goal: "g",
      status: "open",
      conversationId: null,
      procedureId: null,
      procedureStepIndex: null,
      createdAt: 0,
      updatedAt: 0,
    })
    let updatedPayload: TaskRecord | undefined
    const wrapped: TaskStore = {
      ...taskStore,
      update: async (record) => {
        updatedPayload = record
        return taskStore.update(record)
      },
    }
    const wrappedWiring: Wiring = { ...wiring, taskStore: wrapped }
    const result = await tryWechatTaskCommand({
      wiring: wrappedWiring,
      fromUserId: "u-done",
      content: `/完成 ${task.id}`,
      env,
    })
    expect(result?.reply).toContain("即将标记完成")
    expect(result?.reply).toContain("确认")
    expect(updatedPayload).toBeUndefined()
  })

  it("/完成 <id> 确认 marks the task as done via store.update", async () => {
    const task = await taskStore.create({
      id: randomUUID(),
      subject: "u-done",
      title: "[WFXM] to finish",
      goal: "g",
      status: "open",
      conversationId: null,
      procedureId: null,
      procedureStepIndex: null,
      createdAt: 0,
      updatedAt: 0,
    })
    let updatedPayload: TaskRecord | undefined
    const wrapped: TaskStore = {
      ...taskStore,
      update: async (record) => {
        updatedPayload = record
        return taskStore.update(record)
      },
    }
    const wrappedWiring: Wiring = { ...wiring, taskStore: wrapped }
    const result = await tryWechatTaskCommand({
      wiring: wrappedWiring,
      fromUserId: "u-done",
      content: `/完成 ${task.id} 确认`,
      env,
    })
    expect(result?.reply).toBe(`待办 ${task.id.slice(0, 8)} 已标记完成。`)
    expect(updatedPayload).toBeDefined()
    if (!updatedPayload) throw new Error("updatedPayload should be captured")
    expect(updatedPayload.status).toBe("done")
    const reloaded = await taskStore.get(task.id)
    expect(reloaded?.status).toBe("done")
  })

  it("/完成 with no token returns usage", async () => {
    const result = await tryWechatTaskCommand({
      wiring,
      fromUserId: "u-done-usage",
      content: "/完成",
      env,
    })
    expect(result?.reply).toBe("用法：/完成 <待办id前缀> [--force]")
    expect(result?.traces).toContain("wechat-task: done usage")
  })

  it("/完成 with unknown token returns not-found reply", async () => {
    const result = await tryWechatTaskCommand({
      wiring,
      fromUserId: "u-done-404",
      content: "/完成 deadbeef",
      env,
    })
    expect(result?.reply).toContain("未找到待办「deadbeef」")
    expect(result?.traces).toContain("wechat-task: done not found")
  })

  it("/完成 when store.get returns null after resolveTaskByToken hit (race) returns done-missing trace", async () => {
    const task = await taskStore.create({
      id: randomUUID(),
      subject: "u-done-race",
      title: "[WFXM] race",
      goal: "g",
      status: "open",
      conversationId: null,
      procedureId: null,
      procedureStepIndex: null,
      createdAt: 0,
      updatedAt: 0,
    })
    const wrapped: TaskStore = {
      ...taskStore,
      get: async (id) => {
        if (id === task.id) return null
        return taskStore.get(id)
      },
    }
    const wrappedWiring: Wiring = { ...wiring, taskStore: wrapped }
    const result = await tryWechatTaskCommand({
      wiring: wrappedWiring,
      fromUserId: "u-done-race",
      content: `/完成 ${task.id}`,
      env,
    })
    expect(result?.reply).toContain("未找到待办")
    expect(result?.traces).toContain("wechat-task: done missing")
  })
})

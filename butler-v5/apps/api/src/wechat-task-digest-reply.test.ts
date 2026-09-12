import { mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { makeTestDb } from "@butler/persistence/testing.js"
import { EventBridge } from "@butler/persistence/event-bridge.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import {
  createProjectKnowledgeStore,
  createTaskStore,
  createDurableMemoryStore,
  type DurableMemoryStore,
  type TaskStore,
} from "@butler/persistence"
import { makeWiring, type Wiring } from "./wiring.js"
import { formatTaskDigestReply } from "./wechat-task-digest-reply.js"

describe("formatTaskDigestReply", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let wiring: Wiring
  let testEnv: NodeJS.ProcessEnv
  let storeDir = ""

  beforeEach(async () => {
    db = await makeTestDb()
    const bridge = new EventBridge({ db: db.db, workerId: "task-digest-test" })
    wiring = makeWiring({
      bridge,
      workerId: "task-digest-test",
      runtimeStore: createRuntimeStore(db.db),
      runEngine: new RunEngine(createRuntimeStore(db.db)),
      db: db.db,
      backfillConversation: async () => undefined,
      projectKnowledgeStore: createProjectKnowledgeStore(db.db),
      taskStore: createTaskStore(db.db),
      durableMemoryStore: createDurableMemoryStore(db.db),
    })
    storeDir = mkdtempSync(join(tmpdir(), "butler-task-digest-"))
    testEnv = {
      BUTLER_V5_WECHAT_ACTIVE_PROJECT_STORE: join(storeDir, "active.json"),
      BUTLER_V5_PROJECT_KNOWLEDGE_INBOUND_MAP: "wechat:WFXM",
      BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH: join(process.cwd(), "config/wechat-tool-allowlist.json"),
      BUTLER_V5_WECHAT_PROJECT_PATHS: join(process.cwd(), "config/wechat-project-paths.json"),
      BUTLER_V5_WORKSPACE_ROOT: join(process.cwd(), ".."),
    }
  })

  afterEach(async () => {
    await db.close()
    if (storeDir) rmSync(storeDir, { recursive: true, force: true })
  })

  it("composes 3 segments with header + footer; empty sections read 暂无", async () => {
    const result = await formatTaskDigestReply({
      wiring,
      fromUserId: "u-digest",
      env: testEnv,
    })
    // Header + section markers + footer present
    expect(result.reply).toMatch(/【任务摘要 · wechat】/)
    expect(result.reply).toContain("【项目状态】")
    expect(result.reply).toMatch(/【开放待办】/u)
    expect(result.reply).toMatch(/【候选记忆】/u)
    expect(result.reply).toContain("如需详情：/状态 · /待办 · /记忆候选")
    // Empty sections show the digest-context 暂无 wording (per owner choice)
    expect(result.reply).toContain("暂无开放待办。")
    expect(result.reply).toContain("暂无待审记忆。")
  })

  it("zero LLM: iterations=0, toolCalls=0; finalDecision=Respond", async () => {
    const result = await formatTaskDigestReply({
      wiring,
      fromUserId: "u-digest",
      env: testEnv,
    })
    expect(result.iterations).toBe(0)
    expect(result.toolCalls).toBe(0)
    expect(result.finalDecision).toBe("Respond")
    // Trace tags must mark the path so §14 observability can distinguish
    // task_digest from a regular LLM-driven loop.
    expect(result.traces).toContain("intake:task_digest")
    expect(result.traces.some((t) => t.startsWith("task-digest:active="))).toBe(true)
    expect(result.traces.some((t) => t.startsWith("task-digest:failed="))).toBe(true)
  })

  it("truncates body at 1500 chars and appends 截断 note", async () => {
    // 1) Empty body reference (no data, ~few hundred chars)
    const empty = await formatTaskDigestReply({ wiring, fromUserId: "u-digest", env: testEnv })
    expect(empty.reply.length).toBeLessThan(1500)

    // 2) Construct a task store that returns many long items to exceed the cap.
    //    We bypass the real createTaskStore to force the data shape without
    //    having to insert 60 rows.
    const longTitle = "x".repeat(80)
    const fakeTaskStore: TaskStore = {
      create: async () => { throw new Error("not used") },
      get: async () => null,
      update: async () => { throw new Error("not used") },
      listBySubject: async () =>
        Array.from({ length: 60 }, (_, i) => ({
          id: `t-${i.toString().padStart(2, "0")}-pad-pad`,
          subject: "u-digest",
          title: `[wechat] ${longTitle}-${i}`,
          goal: "y".repeat(120),
          status: "open" as const,
          conversationId: null,
          procedureId: null,
          procedureStepIndex: null,
          createdAt: 0,
          updatedAt: 0,
        })),
    }
    const fakeWiring: Wiring = {
      ...wiring,
      taskStore: fakeTaskStore,
    }
    const result = await formatTaskDigestReply({
      wiring: fakeWiring,
      fromUserId: "u-digest",
      env: testEnv,
    })
    expect(result.reply.length).toBeLessThanOrEqual(1500)
    expect(result.reply).toContain("摘要过长")
  })

  it("isolates failures: one section throwing does not blank the others", async () => {
    // Make only the memory store throw. Status + tasks should still render
    // (they use projectKnowledgeStore / taskStore respectively), and the
    // candidates section should fall back to the failure message.
    const throwingMemoryStore = {
      create: async () => { throw new Error("not used") },
      get: async () => null,
      update: async () => { throw new Error("not used") },
      delete: async () => false,
      listBySubject: async () => {
        throw new Error("simulated memory outage")
      },
      countBySubject: async () => 0,
      listExpiredCandidates: async () => [],
      markExpired: async () => [],
    } as unknown as DurableMemoryStore
    const failWiring: Wiring = {
      ...wiring,
      durableMemoryStore: throwingMemoryStore,
    }
    const result = await formatTaskDigestReply({
      wiring: failWiring,
      fromUserId: "u-digest",
      env: testEnv,
    })
    // Failure fallback visible for candidates
    expect(result.reply).toContain("记忆候选查询失败")
    // Status and tasks sections still render (no exception propagated)
    expect(result.reply).toContain("【项目状态】")
    expect(result.reply).toContain("【开放待办】")
    // failed=1 surfaced for §14 observability
    const failedTrace = result.traces.find((t) => t.startsWith("task-digest:failed="))
    expect(failedTrace).toBe("task-digest:failed=1")
  })

  it("surfaces per-store failure reason inline so owner can diagnose which backend is down", async () => {
    // Audit finding (D55 SF-01): allSettled swallowing means owner sees only
    // generic "查询失败" — operators cannot tell whether status / tasks /
    // candidates backend is degraded. Inline reason is the minimal signal.
    const throwingMemoryStore = {
      create: async () => { throw new Error("not used") },
      get: async () => null,
      update: async () => { throw new Error("not used") },
      delete: async () => false,
      listBySubject: async () => {
        throw new Error("simulated memory outage")
      },
      countBySubject: async () => 0,
      listExpiredCandidates: async () => [],
      markExpired: async () => [],
    } as unknown as DurableMemoryStore
    const failWiring: Wiring = {
      ...wiring,
      durableMemoryStore: throwingMemoryStore,
    }
    const result = await formatTaskDigestReply({
      wiring: failWiring,
      fromUserId: "u-digest",
      env: testEnv,
    })
    // Owner sees which backend is broken (the actual error reason)
    expect(result.reply).toContain("simulated memory outage")
    // Trace now carries per-store failure details for §14 observability
    const reasonTrace = result.traces.find((t) => t.startsWith("task-digest:reason="))
    expect(reasonTrace).toBeDefined()
    expect(reasonTrace).toContain("candidates")
    expect(reasonTrace).toContain("simulated memory outage")
  })
})

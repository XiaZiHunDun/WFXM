/**
 * P4 real-path acceptance (no iLink, no Web UI).
 * Simulates WeChat HTTP inbound + Schedule fire + Task/Procedure + Owner traces.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { eq } from "drizzle-orm"
import { Hono } from "hono"
import { EventBridge } from "@butler/runtime/bridge.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { resetSharedLocalTracer } from "@butler/runtime/observability/local-tracer.js"
import {
  createProcedureStore,
  createRuntimeStore,
  createTaskStore,
  listMigrationFiles,
} from "@butler/persistence"
import { runs } from "@butler/persistence/schema.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import { makeWiring, type Wiring } from "./wiring.js"
import { createRoutes } from "./routes.js"
import { createOwnerRoutes } from "./owner-routes.js"
import { runScheduleJob } from "./schedule-run.js"
import type { ScheduleJobSpec } from "@butler/domain/runtime.js"

describe("P4 acceptance harness", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let wiring: Wiring
  let app: Hono

  beforeEach(async () => {
    resetSharedLocalTracer({
      BUTLER_V5_TRACE: "1",
      BUTLER_V5_TRACE_REDACT: "1",
      BUTLER_V5_OTEL_EXPORTER: "off",
    })
    db = await makeTestDb()
    const bridge = new EventBridge({ db: db.db, workerId: "w-p4-accept" })
    const runtimeStore = createRuntimeStore(db.db)
    wiring = makeWiring({
      bridge,
      workerId: "w-p4-accept",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      procedureStore: createProcedureStore(db.db),
      taskStore: createTaskStore(db.db),
      backfillConversation: async () => undefined,
    })
    app = new Hono()
    createRoutes(app, wiring)
    createOwnerRoutes(app, wiring)
  })

  afterEach(async () => {
    await db.close()
  })

  it("migrations 0004–0006 and 0010 are registered", () => {
    const files = listMigrationFiles()
    expect(files).toContain("0004_durable_memory.sql")
    expect(files).toContain("0005_documents.sql")
    expect(files).toContain("0006_task_procedure.sql")
    expect(files).toContain("0010_project_knowledge.sql")
  })

  it("wechat inbound → schedule → task step → owner traces", async () => {
    const ownerHeaders = {
      "content-type": "application/json",
    }

    // 1) Simulate WeChat message (HTTP intake, no iLink)
    const wxConversationId = "c-p4-wechat-accept"
    const wxRes = await app.request("/v1/wechat/inbound", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        apiVersion: "v1",
        fromUserId: "wx-owner-1",
        content: "帮我只读巡检一下",
        projectId: "wechat",
        conversationId: wxConversationId,
        messageId: "msg-p4-accept-1",
      }),
    })
    expect(wxRes.status).toBe(201)
    const wxBody = (await wxRes.json()) as {
      conversationId: string
      reply: string
      meta: { finalDecision: string }
    }
    expect(wxBody.conversationId).toBe(wxConversationId)
    expect(wxBody.reply.length).toBeGreaterThan(0)
    expect(wxBody.meta.finalDecision).toBeTruthy()

    const [wxRun] = await db
      .select()
      .from(runs)
      .where(eq(runs.conversationId, wxConversationId))
    expect(wxRun?.triggerSource).toBe("channel")
    expect(wxRun?.subject).toBe("wx-owner-1")

    // 2) Schedule fire (same RunEngine path, source=schedule)
    const job: ScheduleJobSpec = {
      id: "p4-heartbeat",
      everyMs: 60_000,
      goal: "只读巡检，无事回复无事",
      cooldownMs: 1_000,
      maxSteps: 3,
      deadlineMs: 120_000,
      quietSuccess: true,
      enabled: true,
    }
    const scheduleConversationId = "schedule-p4-heartbeat"
    await runScheduleJob({
      wiring,
      job,
      conversationId: scheduleConversationId,
      idempotencyKey: "schedule:p4-heartbeat:accept",
      deadline: new Date("2026-08-21T12:02:00Z"),
      env: {},
    })
    const [schedRun] = await db
      .select()
      .from(runs)
      .where(eq(runs.conversationId, scheduleConversationId))
    expect(schedRun?.triggerSource).toBe("schedule")
    expect(schedRun?.subject).toBe("system:scheduler")

    // 3) Task + Procedure step via Owner API
    const procRes = await app.request("/v1/owner/procedures", {
      method: "POST",
      headers: ownerHeaders,
      body: JSON.stringify({
        name: "p4-巡检手册",
        steps: [
          { key: "check", title: "检查", goal: "只读巡检" },
          { key: "report", title: "汇报", goal: "写摘要" },
        ],
      }),
    })
    expect(procRes.status).toBe(200)
    const procBody = (await procRes.json()) as { ok: boolean; item: { id: string } }
    expect(procBody.ok).toBe(true)

    const taskRes = await app.request("/v1/owner/tasks", {
      method: "POST",
      headers: ownerHeaders,
      body: JSON.stringify({
        subject: "owner",
        title: "今日巡检",
        goal: "只读巡检",
        procedureId: procBody.item.id,
        procedureStepIndex: 0,
      }),
    })
    const taskBody = (await taskRes.json()) as { ok: boolean; item: { id: string } }
    expect(taskBody.ok).toBe(true)

    const runRes = await app.request(`/v1/owner/tasks/${taskBody.item.id}/run`, {
      method: "POST",
      headers: ownerHeaders,
      body: "{}",
    })
    expect(runRes.status).toBe(200)
    const runBody = (await runRes.json()) as {
      ok: boolean
      goal: string
      stepKey: string | null
      task: { procedureStepIndex: number | null; goal: string }
    }
    expect(runBody.ok).toBe(true)
    expect(runBody.goal).toBe("只读巡检")
    expect(runBody.stepKey).toBe("check")
    expect(runBody.task.procedureStepIndex).toBe(1)
    expect(runBody.task.goal).toBe("写摘要")

    const taskConversationId = `task-${taskBody.item.id}`
    const [taskRun] = await db
      .select()
      .from(runs)
      .where(eq(runs.conversationId, taskConversationId))
    expect(taskRun?.triggerSource).toBe("task")

    // 4) Traces visible via Owner API for each conversation
    for (const conversationId of [
      wxConversationId,
      scheduleConversationId,
      taskConversationId,
    ]) {
      const tr = await app.request(
        `/v1/owner/traces?conversationId=${encodeURIComponent(conversationId)}`,
      )
      expect(tr.status).toBe(200)
      const body = (await tr.json()) as {
        enabled: boolean
        items: readonly { kind: string; name: string }[]
      }
      expect(body.enabled).toBe(true)
      expect(body.items.some((e) => e.kind === "run" && e.name === "start")).toBe(true)
      expect(body.items.some((e) => e.kind === "run" && e.name === "finish")).toBe(true)
    }
  })
})

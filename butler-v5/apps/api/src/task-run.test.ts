import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { eq } from "drizzle-orm"
import { Hono } from "hono"
import { EventBridge } from "@butler/runtime/bridge.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import {
  createProcedureStore,
  createRuntimeStore,
  createTaskStore,
} from "@butler/persistence"
import { runs } from "@butler/persistence/schema.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import { makeWiring, type Wiring } from "./wiring.js"
import { createOwnerRoutes } from "./owner-routes.js"
import { runTaskGoal } from "./task-run.js"

describe("task / procedure owner + run", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let wiring: Wiring
  let app: Hono

  beforeEach(async () => {
    db = await makeTestDb()
    const bridge = new EventBridge({ db: db.db, workerId: "w-task" })
    const runtimeStore = createRuntimeStore(db.db)
    wiring = makeWiring({
      bridge,
      workerId: "w-task",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      procedureStore: createProcedureStore(db.db),
      taskStore: createTaskStore(db.db),
      backfillConversation: async () => undefined,
    })
    app = new Hono()
    createOwnerRoutes(app, wiring)
  })

  afterEach(async () => {
    await db.close()
  })

  it("creates procedure/task and runs via task Trigger", async () => {
    const procRes = await app.request("/v1/owner/procedures", {
      method: "POST",
      headers: {
        "content-type": "application/json",
      },
      body: JSON.stringify({
        name: "巡检",
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
      headers: {
        "content-type": "application/json",
      },
      body: JSON.stringify({
        title: "今日巡检",
        goal: "只读巡检",
        procedureId: procBody.item.id,
        procedureStepIndex: 0,
      }),
    })
    const taskBody = (await taskRes.json()) as { ok: boolean; item: { id: string } }
    expect(taskBody.ok).toBe(true)

    const result = await runTaskGoal({
      wiring,
      taskId: taskBody.item.id,
      env: {},
    })
    expect(result.goal).toBe("只读巡检")
    expect(result.task.procedureStepIndex).toBe(1)
    expect(result.task.goal).toBe("写摘要")

    const [run] = await db
      .select()
      .from(runs)
      .where(eq(runs.conversationId, `task-${taskBody.item.id}`))
    expect(run?.triggerSource).toBe("task")
    expect(run?.budget).toMatchObject({
      trustLevel: "owner",
      triggerPayload: expect.objectContaining({ taskId: taskBody.item.id }),
    })
  })
})

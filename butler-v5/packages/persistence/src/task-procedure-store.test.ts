import { describe, expect, it } from "vitest"
import {
  createProcedureRecord,
  createTaskRecord,
} from "@butler/domain/knowledge/task-procedure.js"
import { createProcedureStore, createTaskStore } from "./task-procedure-store.js"
import { makeTestDb } from "./testing.js"

describe("taskProcedureStore", () => {
  it("persists procedure and task", async () => {
    const db = await makeTestDb()
    try {
      const procedures = createProcedureStore(db.db)
      const tasks = createTaskStore(db.db)
      const proc = createProcedureRecord({
        name: "巡检",
        steps: [{ key: "a", title: "A", goal: "做 A" }],
        nowMs: 1,
      })
      expect(proc.ok).toBe(true)
      if (!proc.ok) return
      await procedures.create(proc.value)

      const task = createTaskRecord({
        subject: "owner",
        title: "跑巡检",
        goal: "做 A",
        procedureId: proc.value.id,
        procedureStepIndex: 0,
        nowMs: 2,
      })
      expect(task.ok).toBe(true)
      if (!task.ok) return
      await tasks.create(task.value)
      const listed = await tasks.listBySubject({ subject: "owner", status: "open" })
      expect(listed).toHaveLength(1)
      expect(await procedures.get(proc.value.id)).toMatchObject({ name: "巡检", version: 1 })
    } finally {
      await db.close()
    }
  })
})

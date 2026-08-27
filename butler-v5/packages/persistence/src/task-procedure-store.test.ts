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

  it("persists advance, filters by status, and returns null for missing", async () => {
    const db = await makeTestDb()
    try {
      const procedures = createProcedureStore(db.db)
      const tasks = createTaskStore(db.db)
      const proc = createProcedureRecord({
        name: "三步",
        steps: [
          { key: "a", title: "A", goal: "ga" },
          { key: "b", title: "B", goal: "gb" },
        ],
        nowMs: 1,
      })
      const task = createTaskRecord({
        subject: "owner",
        title: "跑",
        goal: "ga",
        procedureId: proc.value.id,
        procedureStepIndex: 0,
        nowMs: 2,
      })
      expect(proc.ok && task.ok).toBe(true)
      if (!proc.ok || !task.ok) return
      await procedures.create(proc.value)
      await tasks.create(task.value)

      await tasks.update({ ...task.value, goal: "gb", procedureStepIndex: 1, updatedAt: 3 })
      const got = await tasks.get(task.value.id)
      expect(got?.procedureStepIndex).toBe(1)
      expect(got?.goal).toBe("gb")

      await tasks.update({ ...task.value, goal: "gb", procedureStepIndex: 1, status: "done", updatedAt: 4 })
      expect(await tasks.listBySubject({ subject: "owner", status: "open" })).toHaveLength(0)
      expect(await tasks.listBySubject({ subject: "owner", status: "done" })).toHaveLength(1)
      expect(await tasks.get("ffffffff-ffff-ffff-ffff-ffffffffffff")).toBeNull()
    } finally {
      await db.close()
    }
  })
})

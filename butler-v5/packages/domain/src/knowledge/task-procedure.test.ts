import { describe, expect, it } from "vitest"
import {
  advanceTaskAfterStep,
  createProcedureRecord,
  createTaskRecord,
  resolveTaskRunGoal,
} from "./task-procedure.js"

describe("task / procedure", () => {
  it("creates immutable linear procedure and resolves step goals", () => {
    const proc = createProcedureRecord({
      id: "proc-1",
      name: "巡检手册",
      steps: [
        { key: "check", title: "检查", goal: "只读巡检" },
        { key: "report", title: "汇报", goal: "写摘要" },
      ],
      nowMs: 1,
    })
    expect(proc.ok).toBe(true)
    if (!proc.ok) return

    const task = createTaskRecord({
      subject: "owner",
      title: "今日巡检",
      goal: "只读巡检",
      procedureId: "proc-1",
      procedureStepIndex: 0,
      nowMs: 2,
    })
    expect(task.ok).toBe(true)
    if (!task.ok) return

    const resolved = resolveTaskRunGoal(task.value, proc.value)
    expect(resolved).toEqual({ ok: true, goal: "只读巡检", stepKey: "check" })

    const advanced = advanceTaskAfterStep(task.value, proc.value, 3)
    expect(advanced.procedureStepIndex).toBe(1)
    expect(advanced.goal).toBe("写摘要")
    expect(advanceTaskAfterStep(advanced, proc.value, 4).status).toBe("done")
  })

  it("rejects empty procedure steps", () => {
    expect(createProcedureRecord({ name: "x", steps: [] }).ok).toBe(false)
  })
})

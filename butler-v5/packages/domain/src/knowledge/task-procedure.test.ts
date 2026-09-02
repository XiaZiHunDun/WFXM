import { describe, expect, it } from "vitest"
import {
  advanceTaskAfterStep,
  createProcedureRecord,
  createTaskRecord,
  resolveTaskRunGoal,
} from "./task-procedure.js"
import { defaultTaskConversationId } from "./task-procedure.js"

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

  it("rejects duplicate step keys and version < 1", () => {
    expect(
      createProcedureRecord({
        name: "x",
        steps: [
          { key: "a", title: "A", goal: "ga" },
          { key: "a", title: "A2", goal: "ga2" },
        ],
      }).ok,
    ).toBe(false)
    expect(
      createProcedureRecord({
        name: "x",
        version: 0,
        steps: [{ key: "a", title: "A", goal: "ga" }],
      }).ok,
    ).toBe(false)
  })

  it("validates task fields (goal/status/index)", () => {
    expect(
      createTaskRecord({ subject: "owner", title: "t", goal: " ", nowMs: 1 }).ok,
    ).toBe(false)
    expect(
      createTaskRecord({
        subject: "owner",
        title: "t",
        goal: "g",
        status: "bogus",
        nowMs: 1,
      }).ok,
    ).toBe(false)
    expect(
      createTaskRecord({
        subject: "owner",
        title: "t",
        goal: "g",
        procedureStepIndex: -1,
        nowMs: 1,
      }).ok,
    ).toBe(false)
  })

  it("resolves free-form task goal and fails on not-open / mismatch / out-of-range", () => {
    const proc = createProcedureRecord({
      id: "p1",
      name: "巡检",
      steps: [{ key: "s0", title: "S0", goal: "干 S0" }],
      nowMs: 1,
    })
    const task = createTaskRecord({
      id: "t1",
      subject: "owner",
      title: "t",
      goal: "自由目标",
      procedureId: "p1",
      procedureStepIndex: 0,
      nowMs: 2,
    })
    expect(proc.ok && task.ok).toBe(true)
    if (!proc.ok || !task.ok) return

    expect(resolveTaskRunGoal(task.value, proc.value)).toEqual({
      ok: true,
      goal: "干 S0",
      stepKey: "s0",
    })

    const freeForm = { ...task.value, procedureId: null, procedureStepIndex: null }
    expect(resolveTaskRunGoal(freeForm, proc.value)).toEqual({
      ok: true,
      goal: "自由目标",
      stepKey: null,
    })

    const done = { ...task.value, status: "done" }
    expect(resolveTaskRunGoal(done, proc.value)).toEqual({ ok: false, reason: "task is done" })

    expect(resolveTaskRunGoal(task.value, { ...proc.value, id: "other" })).toMatchObject({
      ok: false,
    })

    expect(
      resolveTaskRunGoal({ ...task.value, procedureStepIndex: 5 }, proc.value),
    ).toMatchObject({ ok: false })
  })

  it("advance marks task done when past last step", () => {
    const proc = createProcedureRecord({
      id: "p2",
      name: "单步",
      steps: [{ key: "only", title: "Only", goal: "只做一次" }],
      nowMs: 1,
    })
    const task = createTaskRecord({
      id: "t2",
      subject: "owner",
      title: "t",
      goal: "g",
      procedureId: "p2",
      procedureStepIndex: 0,
      nowMs: 2,
    })
    expect(proc.ok && task.ok).toBe(true)
    if (!proc.ok || !task.ok) return
    const advanced = advanceTaskAfterStep(task.value, proc.value, 3)
    expect(advanced.status).toBe("done")
    expect(advanced.procedureStepIndex).toBe(0)
  })
})

describe("defaultTaskConversationId", () => {
  it("namespaces conversation id by task id", () => {
    expect(defaultTaskConversationId("42")).toBe("task-42")
    expect(defaultTaskConversationId(" task-7 ")).toBe("task- task-7 ")
  })
})

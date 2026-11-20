import { describe, expect, it } from "vitest"
import type {
  ButlerMemoryPort,
  ButlerSessionSummaryEvent,
} from "@butler/ports/core/butler-memory.js"
import type { ButlerTaskPort, ButlerTaskRef } from "@butler/ports/core/butler-task.js"
import {
  ButlerRuntime,
  MemoryButlerSessionStore,
  matchButlerRule,
  type ButlerModelPort,
  type ButlerModelReply,
} from "./index.js"

interface ModelRequest {
  readonly messages: readonly { role: string; content: string }[]
  readonly tools?: readonly { name: string }[]
}

function fakeModel(replies: readonly ButlerModelReply[] = []): ButlerModelPort & {
  readonly requests: ModelRequest[]
} {
  const requests: ModelRequest[] = []
  let index = 0
  return {
    requests,
    async complete(request) {
      requests.push({
        messages: request.messages.map((message) => ({
          role: message.role,
          content: message.content,
        })),
        ...(request.tools === undefined ? {} : { tools: request.tools }),
      })
      const reply = replies[Math.min(index, replies.length - 1)] ?? { content: "好的" }
      index += 1
      return reply
    },
  }
}

function fakeTasks(initial: readonly ButlerTaskRef[] = []): ButlerTaskPort & {
  readonly started: { projectId: string; goal: string }[]
  readonly approvals: { taskId: string; approved: boolean }[]
} {
  const tasks = [...initial]
  const started: { projectId: string; goal: string }[] = []
  const approvals: { taskId: string; approved: boolean }[] = []
  return {
    started,
    approvals,
    async start(input) {
      started.push({ projectId: input.projectId, goal: input.goal })
      const task: ButlerTaskRef = {
        taskId: `task-${started.length}`,
        projectId: input.projectId,
        status: "idle",
        summary: input.goal,
      }
      tasks.push(task)
      return task
    },
    async status(taskId) {
      return tasks.find((task) => task.taskId === taskId) ?? null
    },
    async list(projectId) {
      return projectId ? tasks.filter((task) => task.projectId === projectId) : tasks
    },
    async approve(taskId, approved) {
      approvals.push({ taskId, approved })
      const task = tasks.find((entry) => entry.taskId === taskId)
      return task ? { ...task, status: "idle" } : null
    },
  }
}

function fakeMemory(): ButlerMemoryPort & { readonly events: ButlerSessionSummaryEvent[] } {
  const events: ButlerSessionSummaryEvent[] = []
  return {
    events,
    async recordSessionSummary(event) {
      events.push(event)
    },
    async recallUserMemory() {
      return [{ title: "用户画像", text: "偏好先结论后细节" }]
    },
  }
}

let clockTick = 0
const clock = () => `2026-11-17T10:00:0${Math.min(clockTick++, 9)}Z`

describe("matchButlerRule", () => {
  it("matches explicit commands only", () => {
    expect(matchButlerRule({ content: "/help" })).toMatchObject({ kind: "reply", name: "help" })
    expect(matchButlerRule({ content: "帮助" })).toMatchObject({ kind: "reply", name: "help" })
    expect(matchButlerRule({ content: "/new 修复登录超时" })).toMatchObject({
      kind: "start_task",
      goal: "修复登录超时",
    })
    expect(matchButlerRule({ content: "新任务：补一版 README" })).toMatchObject({
      kind: "start_task",
      goal: "补一版 README",
    })
    expect(matchButlerRule({ content: "/new" })).toMatchObject({ kind: "reply", name: "new-usage" })
    expect(matchButlerRule({ content: "/tasks" })).toMatchObject({ kind: "list_tasks" })
    expect(matchButlerRule({ content: "状态" })).toMatchObject({ kind: "list_tasks" })
    expect(matchButlerRule({ content: "状态", activeTaskId: "t1" })).toMatchObject({
      kind: "task_status",
      taskId: "t1",
    })
    expect(matchButlerRule({ content: "确认", activeTaskId: "t1" })).toMatchObject({
      kind: "approve",
      approved: true,
    })
    expect(matchButlerRule({ content: "拒绝", activeTaskId: "t1" })).toMatchObject({
      kind: "approve",
      approved: false,
    })
    expect(matchButlerRule({ content: "确认" })).toBeNull()
    expect(matchButlerRule({ content: "帮我看看登录为什么超时" })).toBeNull()
  })
})

describe("ButlerRuntime", () => {
  it("answers help without calling the model", async () => {
    const model = fakeModel()
    const runtime = new ButlerRuntime({ model, clock })
    const result = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      content: "/help",
    })
    expect(result.route).toBe("rule")
    expect(result.rule).toBe("help")
    expect(result.reply).toContain("/new <目标>")
    expect(result.usage.totalTokens).toBe(0)
    expect(model.requests).toHaveLength(0)
  })

  it("starts a task from a /new rule", async () => {
    const model = fakeModel()
    const tasks = fakeTasks()
    const runtime = new ButlerRuntime({ model, tasks, clock })
    const result = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "p1",
      content: "/new 修复登录超时",
    })
    expect(result.route).toBe("rule")
    expect(result.taskId).toBe("task-1")
    expect(tasks.started).toEqual([{ projectId: "p1", goal: "修复登录超时" }])
    expect(model.requests).toHaveLength(0)
  })

  it("forwards approval decisions to the task layer", async () => {
    const tasks = fakeTasks([{ taskId: "t1", projectId: "p1", status: "paused" }])
    const runtime = new ButlerRuntime({ model: fakeModel(), tasks, clock })
    const result = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "p1",
      content: "确认",
      activeTaskId: "t1",
    })
    expect(result.rule).toBe("approve")
    expect(tasks.approvals).toEqual([{ taskId: "t1", approved: true }])
  })

  it("runs the agent channel and keeps the transcript", async () => {
    const model = fakeModel([
      { content: "登录超时通常是网关超时设置过短。" },
      { content: "建议先看网关日志。" },
    ])
    const runtime = new ButlerRuntime({ model, clock })
    await runtime.handle({ conversationId: "c1", userId: "u1", content: "登录为什么超时？" })
    const second = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      content: "那我该看哪里？",
    })

    expect(second.route).toBe("agent")
    expect(model.requests).toHaveLength(2)
    const secondRequest = model.requests[1]?.messages ?? []
    expect(secondRequest[0]?.role).toBe("system")
    expect(secondRequest.some((message) => message.content === "登录为什么超时？")).toBe(true)
    expect(
      secondRequest.some((message) => message.content === "登录超时通常是网关超时设置过短。"),
    ).toBe(true)
  })

  it("executes start_task through the butler tool loop", async () => {
    const model = fakeModel([
      {
        content: "",
        toolCalls: [{ id: "call-1", name: "start_task", args: { goal: "补一版 README" } }],
      },
      { content: "已交给任务层。" },
    ])
    const tasks = fakeTasks()
    const runtime = new ButlerRuntime({ model, tasks, clock })
    const result = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "p1",
      content: "顺手补一版 README 吧",
    })

    expect(result.route).toBe("agent")
    expect(result.taskId).toBe("task-1")
    expect(result.reply).toBe("已交给任务层。")
    expect(tasks.started).toEqual([{ projectId: "p1", goal: "补一版 README" }])
    expect(result.traces).toContain("tool:start_task:ok")
  })

  it("injects recalled user memory into the system prompt", async () => {
    const model = fakeModel([{ content: "明白。" }])
    const memory = fakeMemory()
    const runtime = new ButlerRuntime({ model, memory, clock })
    const result = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      content: "以后回答我时注意格式",
    })

    expect(model.requests[0]?.messages[0]?.content).toContain("偏好先结论后细节")
    expect(result.traces).toContain("memory:recall:1")
  })

  it("summarizes a session into structured user memory", async () => {
    const model = fakeModel([
      { content: "好的，以后都用要点回答。" },
      {
        content:
          '```json\n{"summary":"用户要求用要点回答","profile":{"communicationStyle":"要点式"},"facts":[{"kind":"preference","title":"回答格式","text":"用户偏好要点式回答"}]}\n```',
      },
    ])
    const memory = fakeMemory()
    const runtime = new ButlerRuntime({ model, memory, clock })
    await runtime.handle({ conversationId: "c1", userId: "u1", content: "以后都用要点回答" })

    const event = await runtime.summarize("c1")
    expect(event).not.toBeNull()
    expect(event?.summary).toBe("用户要求用要点回答")
    expect(event?.profile?.communicationStyle).toBe("要点式")
    expect(event?.facts?.[0]).toMatchObject({ kind: "preference", title: "回答格式" })
    expect(memory.events).toHaveLength(1)
  })

  it("falls back to a deterministic summary when the model output is not JSON", async () => {
    const model = fakeModel([
      { content: "这个问题需要看日志。" },
      { content: "抱歉，我无法总结。" },
    ])
    const memory = fakeMemory()
    const runtime = new ButlerRuntime({ model, memory, clock })
    await runtime.handle({ conversationId: "c1", userId: "u1", content: "登录为什么超时？" })

    const event = await runtime.summarize("c1")
    expect(event?.summary).toBe("这个问题需要看日志。")
    expect(event?.profile).toBeUndefined()
    expect(memory.events).toHaveLength(1)
  })

  it("restores a session from the injected store", async () => {
    const store = new MemoryButlerSessionStore()
    const modelA = fakeModel([{ content: "第一轮回复" }])
    const runtimeA = new ButlerRuntime({ model: modelA, store, clock })
    await runtimeA.handle({ conversationId: "c1", userId: "u1", content: "第一轮" })

    const modelB = fakeModel([{ content: "第二轮回复" }])
    const runtimeB = new ButlerRuntime({ model: modelB, store, clock })
    await runtimeB.handle({ conversationId: "c1", userId: "u1", content: "第二轮" })

    const request = modelB.requests[0]?.messages ?? []
    expect(request.some((message) => message.content === "第一轮")).toBe(true)
    expect(request.some((message) => message.content === "第一轮回复")).toBe(true)
  })

  it("rejects a conversation bound to another user", async () => {
    const runtime = new ButlerRuntime({ model: fakeModel([{ content: "好的" }]), clock })
    await runtime.handle({ conversationId: "c1", userId: "u1", content: "你好" })
    await expect(
      runtime.handle({ conversationId: "c1", userId: "u2", content: "你好" }),
    ).rejects.toThrow(/belongs to another user/)
  })

  it("includes the approval notice when a /new task pauses", async () => {
    const pausedRef: ButlerTaskRef = {
      taskId: "t1",
      projectId: "p1",
      status: "paused",
      summary: "写 a.txt",
      pending: { toolName: "write", reason: "需要审批" },
    }
    const tasks: ButlerTaskPort = {
      async start() {
        return pausedRef
      },
      async status() {
        return pausedRef
      },
      async list() {
        return [pausedRef]
      },
      async approve() {
        return pausedRef
      },
    }
    const runtime = new ButlerRuntime({ model: fakeModel(), tasks, clock })
    const result = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "p1",
      content: "/new 写 a.txt",
    })
    expect(result.reply).toContain("需要确认")
    expect(result.reply).toContain("回复「确认」继续")
    expect(result.reply).toContain("待执行：修改文件")
  })

  it("surfaces a completed task result instead of only the creation notice", async () => {
    const ref: ButlerTaskRef = {
      taskId: "t1",
      projectId: "p1",
      status: "idle",
      summary: "写 README",
      lastReply: "已补好 README。",
    }
    const tasks: ButlerTaskPort = {
      async start() {
        return ref
      },
      async status() {
        return ref
      },
      async list() {
        return [ref]
      },
    }
    const runtime = new ButlerRuntime({ model: fakeModel(), tasks, clock })
    const result = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "p1",
      content: "/new 写 README",
    })
    expect(result.reply).toContain("已补好 README")
  })

  it("surfaces a failed task reason", async () => {
    const ref: ButlerTaskRef = {
      taskId: "t2",
      projectId: "p1",
      status: "failed",
      summary: "写 README",
      error: "模型超时",
    }
    const tasks: ButlerTaskPort = {
      async start() {
        return ref
      },
      async status() {
        return ref
      },
      async list() {
        return [ref]
      },
    }
    const runtime = new ButlerRuntime({ model: fakeModel(), tasks, clock })
    const result = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "p1",
      content: "/new 写 README",
    })
    expect(result.reply).toContain("模型超时")
  })

  it("shows the pending step from /status", async () => {
    const tasks = fakeTasks([
      {
        taskId: "t1",
        projectId: "p1",
        status: "paused",
        summary: "写 a.txt",
        pending: { toolName: "write", reason: "需要审批" },
      },
    ])
    const runtime = new ButlerRuntime({ model: fakeModel(), tasks, clock })
    const result = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "p1",
      content: "状态",
      activeTaskId: "t1",
    })
    expect(result.reply).toContain("需要确认")
  })

  it("handles a card callback without calling the model", async () => {
    const model = fakeModel()
    const tasks = fakeTasks([
      {
        taskId: "t1",
        projectId: "p1",
        status: "paused",
        summary: "写 a.txt",
        pending: { toolName: "write", reason: "需要审批" },
      },
    ])
    const store = new MemoryButlerSessionStore()
    const runtime = new ButlerRuntime({ model, tasks, store, clock })
    const result = await runtime.handleApprovalCallback({
      conversationId: "c1",
      userId: "u1",
      taskId: "t1",
      approved: true,
    })

    expect(result.route).toBe("rule")
    expect(result.rule).toBe("approval-card")
    expect(result.taskId).toBe("t1")
    expect(result.reply).toContain("已确认")
    expect(tasks.approvals).toEqual([{ taskId: "t1", approved: true }])
    expect(model.requests).toHaveLength(0)

    const session = await store.load("c1")
    expect(session?.messages.at(-2)?.content).toBe("确认")
    expect(session?.messages.at(-1)?.content).toContain("已确认")
  })

  it("returns the next notice when approval pauses on another step", async () => {
    const nextPaused: ButlerTaskRef = {
      taskId: "t1",
      projectId: "p1",
      status: "paused",
      summary: "写 b.txt",
      pending: { toolName: "write", reason: "还需要审批" },
    }
    const tasks: ButlerTaskPort = {
      async start() {
        return nextPaused
      },
      async status() {
        return nextPaused
      },
      async list() {
        return [nextPaused]
      },
      async approve() {
        return nextPaused
      },
    }
    const runtime = new ButlerRuntime({ model: fakeModel(), tasks, clock })
    const result = await runtime.handleApprovalCallback({
      conversationId: "c1",
      userId: "u1",
      taskId: "t1",
      approved: true,
    })
    expect(result.reply).toContain("已确认")
    expect(result.reply).toContain("还需要审批")
    expect(result.reply).toContain("回复「确认」继续")
  })

  it("reports unavailable tasks on a callback", async () => {
    const withoutTasks = new ButlerRuntime({ model: fakeModel(), clock })
    const missing = await withoutTasks.handleApprovalCallback({
      conversationId: "c1",
      userId: "u1",
      taskId: "t1",
      approved: false,
    })
    expect(missing.reply).toContain("任务层尚未接入")

    const withTasks = new ButlerRuntime({ model: fakeModel(), tasks: fakeTasks(), clock })
    const unknown = await withTasks.handleApprovalCallback({
      conversationId: "c1",
      userId: "u1",
      taskId: "nope",
      approved: true,
    })
    expect(unknown.reply).toContain("不在等待审批")
  })

  it("exposes the notice for a paused task", async () => {
    const tasks = fakeTasks([
      {
        taskId: "t1",
        projectId: "p1",
        status: "paused",
        summary: "写 a.txt",
        pending: { toolName: "write", reason: "需要审批" },
      },
    ])
    const runtime = new ButlerRuntime({ model: fakeModel(), tasks, clock })
    const notice = await runtime.approvalNotice("t1")
    expect(notice?.actions.map((action) => action.payload)).toEqual(["approve:t1", "reject:t1"])
    expect(await runtime.approvalNotice("missing")).toBeNull()
  })
})

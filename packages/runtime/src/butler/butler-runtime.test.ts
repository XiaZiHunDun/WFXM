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
        ...(input.conversationId === undefined ? {} : { conversationId: input.conversationId }),
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
    expect(matchButlerRule({ content: "/remember 我偏好要点式" })).toMatchObject({
      kind: "remember",
      text: "我偏好要点式",
    })
    expect(matchButlerRule({ content: "记住：先结论后细节" })).toMatchObject({
      kind: "remember",
      text: "先结论后细节",
    })
    expect(matchButlerRule({ content: "/remember" })).toMatchObject({
      kind: "reply",
      name: "remember-usage",
    })
    expect(matchButlerRule({ content: "/project" })).toMatchObject({ kind: "project" })
    expect(matchButlerRule({ content: "/project lingwen" })).toMatchObject({
      kind: "project",
      projectId: "lingwen",
    })
    expect(matchButlerRule({ content: "切换项目 灵文" })).toMatchObject({
      kind: "project",
      projectId: "灵文",
    })
    expect(matchButlerRule({ content: "项目" })).toMatchObject({ kind: "project" })
    expect(matchButlerRule({ content: "记住昨天说的吗？" })).toBeNull()
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
    expect(result.reply).toContain("/remember <内容>")
    expect(result.reply).toContain("/project [项目ID]")
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

  it("stores an explicit 记住 command in user memory", async () => {
    const written: { userId: string; fact: { kind?: string; title: string; text: string } }[] = []
    const memory: ButlerMemoryPort = {
      async recordSessionSummary() {},
      async rememberUserMemory(input) {
        written.push(input)
      },
    }
    const model = fakeModel()
    const runtime = new ButlerRuntime({ model, memory, clock })
    const result = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      content: "/remember 我偏好先结论后细节",
    })

    expect(result.route).toBe("rule")
    expect(result.rule).toBe("remember")
    expect(result.reply).toContain("已记住")
    expect(written).toEqual([
      {
        userId: "u1",
        fact: { kind: "note", title: "我偏好先结论后细节", text: "我偏好先结论后细节" },
      },
    ])
    expect(model.requests).toHaveLength(0)
  })

  it("explains when explicit memory writes are not wired", async () => {
    const memory: ButlerMemoryPort = { async recordSessionSummary() {} }
    const runtime = new ButlerRuntime({ model: fakeModel(), memory, clock })
    const result = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      content: "记住：有事提前说",
    })

    expect(result.route).toBe("rule")
    expect(result.reply).toContain("没有接入长期记忆")
  })

  it("turns a failing memory write into a readable reply", async () => {
    const memory: ButlerMemoryPort = {
      async recordSessionSummary() {},
      async rememberUserMemory() {
        throw new Error("db down")
      },
    }
    const runtime = new ButlerRuntime({ model: fakeModel(), memory, clock })
    const result = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      content: "/remember 周报周五交",
    })

    expect(result.rule).toBe("remember")
    expect(result.reply).toContain("保存这条记忆时出错")
  })

  it("switches the conversation project and keeps it across restarts", async () => {
    const store = new MemoryButlerSessionStore()
    const tasks = fakeTasks([{ taskId: "t9", projectId: "LingWen1", status: "idle" }])
    const options = {
      model: fakeModel(),
      tasks,
      store,
      clock,
      resolveProjectName: (raw: string) => (raw === "灵文" ? "LingWen1" : null),
    }
    const runtime = new ButlerRuntime(options)

    const switched = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "wechat",
      content: "/project 灵文",
    })
    expect(switched.reply).toContain("已切换到项目 LingWen1")

    const listed = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "wechat",
      content: "/tasks",
    })
    expect(listed.reply).toContain("t9")

    const restarted = new ButlerRuntime(options)
    const again = await restarted.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "wechat",
      content: "/tasks",
    })
    expect(again.reply).toContain("t9")
  })

  it("keeps the current project when the requested one is unknown", async () => {
    const tasks = fakeTasks([{ taskId: "t1", projectId: "p1", status: "idle" }])
    const runtime = new ButlerRuntime({
      model: fakeModel(),
      tasks,
      clock,
      resolveProjectName: () => null,
    })

    const switched = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "p1",
      content: "/project nope",
    })
    expect(switched.reply).toContain("没有找到项目 nope")

    const listed = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "p1",
      content: "/tasks",
    })
    expect(listed.reply).toContain("t1")
  })

  it("shows the current project", async () => {
    const runtime = new ButlerRuntime({
      model: fakeModel(),
      clock,
      resolveProjectName: (raw: string) => (raw === "灵文" ? "LingWen1" : null),
    })
    await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "wechat",
      content: "/project 灵文",
    })

    const current = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "wechat",
      content: "/project",
    })
    expect(current.reply).toContain("当前项目：LingWen1")
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
    expect(unknown.reply).toContain("没有找到任务")
  })

  it("rejects an approval from another conversation", async () => {
    const tasks = fakeTasks([
      {
        taskId: "t1",
        projectId: "p1",
        conversationId: "c2",
        status: "paused",
        pending: { toolName: "write", reason: "需要审批" },
      },
    ])
    const runtime = new ButlerRuntime({ model: fakeModel(), tasks, clock })
    const result = await runtime.handleApprovalCallback({
      conversationId: "c1",
      userId: "u1",
      taskId: "t1",
      approved: true,
    })

    expect(result.reply).toContain("不属于当前会话")
    expect(tasks.approvals).toHaveLength(0)
  })

  it("rejects a rule approval from another conversation", async () => {
    const tasks = fakeTasks([
      {
        taskId: "t1",
        projectId: "p1",
        conversationId: "c2",
        status: "paused",
        pending: { toolName: "write", reason: "需要审批" },
      },
    ])
    const runtime = new ButlerRuntime({ model: fakeModel(), tasks, clock })
    const result = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "p1",
      content: "确认",
      activeTaskId: "t1",
    })

    expect(result.reply).toContain("不属于当前会话")
    expect(tasks.approvals).toHaveLength(0)
  })

  it("distinguishes an already handled approval", async () => {
    const tasks = fakeTasks([{ taskId: "t1", projectId: "p1", status: "idle" }])
    const runtime = new ButlerRuntime({ model: fakeModel(), tasks, clock })
    const result = await runtime.handleApprovalCallback({
      conversationId: "c1",
      userId: "u1",
      taskId: "t1",
      approved: true,
    })

    expect(result.reply).toContain("可能已处理")
    expect(tasks.approvals).toHaveLength(0)
  })

  it("binds a newly created task to the conversation", async () => {
    const tasks = fakeTasks()
    const runtime = new ButlerRuntime({ model: fakeModel(), tasks, clock })
    await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "p1",
      content: "/new 写 README",
    })

    expect((await tasks.list())[0]?.conversationId).toBe("c1")
  })

  it("derives the paused task from the conversation for a bare approval", async () => {
    const tasks = fakeTasks([
      {
        taskId: "t1",
        projectId: "p1",
        conversationId: "c1",
        status: "paused",
        pending: { toolName: "write", reason: "需要审批" },
      },
    ])
    const runtime = new ButlerRuntime({ model: fakeModel(), tasks, clock })
    const result = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "p1",
      content: "确认",
    })

    expect(result.reply).toContain("已确认")
    expect(tasks.approvals).toEqual([{ taskId: "t1", approved: true }])
  })

  it("asks which task when several are pending", async () => {
    const tasks = fakeTasks([
      {
        taskId: "t1",
        projectId: "p1",
        conversationId: "c1",
        status: "paused",
        pending: { toolName: "write", reason: "需要审批" },
      },
      {
        taskId: "t2",
        projectId: "p1",
        conversationId: "c1",
        status: "paused",
        pending: { toolName: "write", reason: "需要审批" },
      },
    ])
    const runtime = new ButlerRuntime({ model: fakeModel(), tasks, clock })
    const result = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "p1",
      content: "确认",
    })

    expect(result.reply).toContain("多个待确认")
    expect(tasks.approvals).toHaveLength(0)
  })

  it("replies when nothing is pending", async () => {
    const model = fakeModel()
    const runtime = new ButlerRuntime({ model, tasks: fakeTasks(), clock })
    const result = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "p1",
      content: "确认",
    })

    expect(result.reply).toContain("没有待确认")
    expect(model.requests).toHaveLength(0)
  })

  it("hides tasks from another project in status", async () => {
    const tasks = fakeTasks([
      {
        taskId: "t2",
        projectId: "p2",
        status: "paused",
        pending: { toolName: "write", reason: "需要审批" },
      },
    ])
    const runtime = new ButlerRuntime({ model: fakeModel(), tasks, clock })
    const result = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "p1",
      content: "状态",
      activeTaskId: "t2",
    })

    expect(result.reply).toContain("没有找到任务")
  })

  it("lets /status target an explicit task id", async () => {
    const tasks = fakeTasks([
      { taskId: "t1", projectId: "p1", conversationId: "c1", status: "idle" },
      {
        taskId: "t2",
        projectId: "p1",
        conversationId: "c1",
        status: "paused",
        pending: { toolName: "write", reason: "需要审批" },
      },
    ])
    const runtime = new ButlerRuntime({ model: fakeModel(), tasks, clock })
    const result = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "p1",
      content: "/status t2",
      activeTaskId: "t1",
    })

    expect(result.rule).toBe("status")
    expect(result.reply).toContain("t2")
  })

  it("points to /tasks when the explicit task id is unknown", async () => {
    const runtime = new ButlerRuntime({ model: fakeModel(), tasks: fakeTasks(), clock })
    const result = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "p1",
      content: "/status nope",
    })

    expect(result.reply).toContain("没有找到任务 nope")
    expect(result.reply).toContain("/tasks")
  })

  it("documents the optional task id in help", async () => {
    const runtime = new ButlerRuntime({ model: fakeModel(), clock })
    const result = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      content: "/help",
    })

    expect(result.reply).toContain("/status [任务ID]")
  })

  it("scopes recalled memory and its cache by user", async () => {
    const calls: { query: string; userId?: string }[] = []
    const memory: ButlerMemoryPort = {
      async recordSessionSummary() {},
      async recallUserMemory(query, _limit, userId) {
        calls.push({ query, ...(userId === undefined ? {} : { userId }) })
        return [{ title: `m-${userId ?? "none"}`, text: "x" }]
      },
    }
    const model = fakeModel([{ content: "a" }, { content: "b" }, { content: "c" }])
    const runtime = new ButlerRuntime({ model, memory, clock })

    await runtime.handle({ conversationId: "c1", userId: "u1", content: "部署进度" })
    await runtime.handle({ conversationId: "c2", userId: "u2", content: "部署进度" })
    expect(calls.map((call) => call.userId)).toEqual(["u1", "u2"])

    await runtime.handle({ conversationId: "c1", userId: "u1", content: "部署进度" })
    expect(calls).toHaveLength(2)
  })

  it("projects memory on a message cadence", async () => {
    const events: ButlerSessionSummaryEvent[] = []
    const memory: ButlerMemoryPort = {
      async recordSessionSummary(event) {
        events.push(event)
      },
      async recallUserMemory() {
        return []
      },
    }
    const runtime = new ButlerRuntime({
      model: fakeModel([{ content: "一" }, { content: "二" }, { content: "summary" }]),
      memory,
      clock,
      summaryEveryMessages: 4,
    })

    await runtime.handle({ conversationId: "c1", userId: "u1", content: "你好" })
    expect(await runtime.summarizeIfDue("c1")).toBeNull()

    await runtime.handle({ conversationId: "c1", userId: "u1", content: "再说一句" })
    const event = await runtime.summarizeIfDue("c1")
    expect(event?.userId).toBe("u1")
    expect(events).toHaveLength(1)
    expect(await runtime.summarizeIfDue("c1")).toBeNull()
  })

  it("keeps the projected summary when memory write fails", async () => {
    const memory: ButlerMemoryPort = {
      async recordSessionSummary() {
        throw new Error("memory down")
      },
      async recallUserMemory() {
        return []
      },
    }
    const runtime = new ButlerRuntime({
      model: fakeModel([{ content: "一" }, { content: "二" }, { content: "summary" }]),
      memory,
      clock,
      summaryEveryMessages: 4,
    })

    await runtime.handle({ conversationId: "c1", userId: "u1", content: "你好" })
    await runtime.handle({ conversationId: "c1", userId: "u1", content: "再来" })
    const event = await runtime.summarizeIfDue("c1")

    expect(event).not.toBeNull()
    expect(event?.userId).toBe("u1")
  })

  it("returns a readable reply when the task layer fails", async () => {
    const tasks: ButlerTaskPort = {
      async start() {
        throw new Error("task layer down")
      },
      async status() {
        return null
      },
      async list() {
        return []
      },
    }
    const store = new MemoryButlerSessionStore()
    const runtime = new ButlerRuntime({ model: fakeModel(), tasks, store, clock })
    const result = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "p1",
      content: "/new 写 README",
    })

    expect(result.reply).toContain("暂时没完成")
    const session = await store.load("c1")
    expect(session?.messages.at(-2)?.content).toBe("/new 写 README")
    expect(session?.messages.at(-1)?.content).toContain("暂时没完成")
  })

  it("returns a readable reply when pending lookup fails", async () => {
    const tasks: ButlerTaskPort = {
      async start() {
        throw new Error("unused")
      },
      async status() {
        return null
      },
      async list() {
        throw new Error("list down")
      },
    }
    const runtime = new ButlerRuntime({ model: fakeModel(), tasks, clock })
    const result = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "p1",
      content: "确认",
    })

    expect(result.reply).toContain("暂时无法查询")
  })

  it("returns a readable reply when approval forwarding fails", async () => {
    const paused: ButlerTaskRef = {
      taskId: "t1",
      projectId: "p1",
      conversationId: "c1",
      status: "paused",
      pending: { toolName: "write", reason: "需要审批" },
    }
    const tasks: ButlerTaskPort = {
      async start() {
        return paused
      },
      async status() {
        return paused
      },
      async list() {
        return [paused]
      },
      async approve() {
        throw new Error("task layer down")
      },
    }
    const runtime = new ButlerRuntime({ model: fakeModel(), tasks, clock })
    const result = await runtime.handleApprovalCallback({
      conversationId: "c1",
      userId: "u1",
      taskId: "t1",
      approved: true,
    })

    expect(result.reply).toContain("审批暂时没提交成功")
  })

  it("still replies when the session store fails", async () => {
    class FailingStore extends MemoryButlerSessionStore {
      override async save(): Promise<void> {
        throw new Error("db down")
      }
    }
    const runtime = new ButlerRuntime({
      model: fakeModel([{ content: "收到" }]),
      store: new FailingStore(),
      clock,
    })

    const rule = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      content: "/help",
    })
    expect(rule.reply).toContain("可用指令")

    const agent = await runtime.handle({
      conversationId: "c1",
      userId: "u1",
      content: "随便聊聊",
    })
    expect(agent.reply).toBe("收到")
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

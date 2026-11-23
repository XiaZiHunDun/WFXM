import { describe, expect, it } from "vitest"
import {
  ButlerRuntime,
  type ButlerModelPort,
  type ButlerModelReply,
} from "@butler/runtime/butler/index.js"
import type { ButlerTaskPort, ButlerTaskRef } from "@butler/ports/core/butler-task.js"
import type { ChannelPort, ChannelRecipient } from "@butler/ports/core/channel.js"
import {
  handleButlerInbound,
  createTaskSettledNotifier,
  formatTaskSettledNotice,
} from "./butler-inbound.js"

const recipient: ChannelRecipient = { address: "user-1", channelKind: "wechat" }

function fakeModel(replies: readonly ButlerModelReply[] = [{ content: "好的" }]) {
  let calls = 0
  let index = 0
  const model: ButlerModelPort & { readonly calls: number } = {
    get calls() {
      return calls
    },
    async complete() {
      calls += 1
      const reply = replies[Math.min(index, replies.length - 1)] ?? { content: "好的" }
      index += 1
      return reply
    },
  }
  return model
}

function fakeTasks(initial: readonly ButlerTaskRef[] = []) {
  const tasks = [...initial]
  const approvals: { taskId: string; approved: boolean }[] = []
  const tasksPort: ButlerTaskPort & {
    readonly approvals: { taskId: string; approved: boolean }[]
  } = {
    approvals,
    async start(input) {
      const task: ButlerTaskRef = {
        taskId: `task-${tasks.length + 1}`,
        projectId: input.projectId,
        status: "idle",
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
      return task ? { ...task, status: "idle", pending: undefined } : null
    },
  }
  return tasksPort
}

function fakeChannel(fail = false): ChannelPort & { readonly sent: string[] } {
  const sent: string[] = []
  return {
    channelKind: "wechat",
    sent,
    async sendText(input) {
      if (fail) return { ok: false, reason: "ilink down" }
      sent.push(input.content)
      return { ok: true, messageId: null }
    },
  }
}

const clock = () => "2026-11-17T10:00:00.000Z"

describe("handleButlerInbound", () => {
  it("routes a normal message through the butler agent and sends the reply", async () => {
    const model = fakeModel([{ content: "先看网关日志。" }])
    const butler = new ButlerRuntime({ model, clock })
    const channel = fakeChannel()

    const outcome = await handleButlerInbound({
      butler,
      channel,
      recipient,
      input: {
        conversationId: "c1",
        userId: "user-1",
        content: "登录为什么超时？",
      },
    })

    expect(outcome.result.route).toBe("agent")
    expect(outcome.sent).toBe(true)
    expect(channel.sent).toEqual(["先看网关日志。"])
    expect(model.calls).toBe(1)
  })

  it("routes a card payload to the task layer without calling the model", async () => {
    const pending: ButlerTaskRef = {
      taskId: "t1",
      projectId: "p1",
      status: "paused",
      pending: { toolName: "write", reason: "需要审批" },
    }
    const model = fakeModel()
    const tasks = fakeTasks([pending])
    const butler = new ButlerRuntime({ model, tasks, clock })
    const channel = fakeChannel()

    const outcome = await handleButlerInbound({
      butler,
      channel,
      recipient,
      input: {
        conversationId: "c1",
        userId: "user-1",
        projectId: "p1",
        content: "",
        approvalPayload: "approve:t1",
      },
    })

    expect(outcome.result.route).toBe("rule")
    expect(outcome.result.rule).toBe("approval-card")
    expect(tasks.approvals).toEqual([{ taskId: "t1", approved: true }])
    expect(model.calls).toBe(0)
    expect(channel.sent[0]).toContain("已确认")
  })

  it("routes a text 确认 reply through the approval rule when a task is active", async () => {
    const pending: ButlerTaskRef = {
      taskId: "t1",
      projectId: "p1",
      status: "paused",
      pending: { toolName: "write", reason: "需要审批" },
    }
    const model = fakeModel()
    const tasks = fakeTasks([pending])
    const butler = new ButlerRuntime({ model, tasks, clock })
    const channel = fakeChannel()

    const outcome = await handleButlerInbound({
      butler,
      channel,
      recipient,
      input: {
        conversationId: "c1",
        userId: "user-1",
        projectId: "p1",
        content: "确认",
        activeTaskId: "t1",
      },
    })

    expect(outcome.result.rule).toBe("approve")
    expect(tasks.approvals).toEqual([{ taskId: "t1", approved: true }])
    expect(model.calls).toBe(0)
  })

  it("rejects an unparsable card payload", async () => {
    const butler = new ButlerRuntime({ model: fakeModel(), clock })
    await expect(
      handleButlerInbound({
        butler,
        channel: fakeChannel(),
        recipient,
        input: {
          conversationId: "c1",
          userId: "user-1",
          content: "",
          approvalPayload: "button-42",
        },
      }),
    ).rejects.toThrow(/invalid approval payload/)
  })

  it("reports delivery failures without dropping the turn result", async () => {
    const butler = new ButlerRuntime({ model: fakeModel([{ content: "收到" }]), clock })
    const outcome = await handleButlerInbound({
      butler,
      channel: fakeChannel(true),
      recipient,
      input: { conversationId: "c1", userId: "user-1", content: "你好" },
    })

    expect(outcome.sent).toBe(false)
    expect(outcome.sendError).toBe("ilink down")
    expect(outcome.result.reply).toBe("收到")
  })

  it("splits a long markdown reply into plain WeChat-sized parts", async () => {
    const paragraph = "这一步先检查网关日志，再对比配置差异。".repeat(40)
    const reply = ["```text", `${paragraph}\n${paragraph}\n${paragraph}`, "```"].join("\n")
    const channel = fakeChannel()

    const outcome = await handleButlerInbound({
      butler: new ButlerRuntime({ model: fakeModel([{ content: reply }]), clock }),
      channel,
      recipient,
      input: { conversationId: "c1", userId: "user-1", content: "说详细点" },
    })

    expect(outcome.sent).toBe(true)
    expect(channel.sent.length).toBeGreaterThan(1)
    for (const part of channel.sent) {
      expect(part.length).toBeLessThanOrEqual(1800)
      expect(part).not.toContain("```")
    }
    expect(channel.sent.join("\n")).not.toContain("```")
  })
})

describe("local WeChat replay", () => {
  const assertPlain = (parts: readonly string[]): void => {
    for (const part of parts) {
      expect(part.trim().length).toBeGreaterThan(0)
      expect(part).not.toMatch(/```|\*\*|^#{1,6}\s/m)
      expect(part.length).toBeLessThanOrEqual(1800)
    }
  }

  it("replays 帮助 as a readable command list", async () => {
    const channel = fakeChannel()
    const outcome = await handleButlerInbound({
      butler: new ButlerRuntime({ model: fakeModel(), clock }),
      channel,
      recipient,
      input: { conversationId: "c1", userId: "user-1", content: "帮助" },
    })

    expect(outcome.result.route).toBe("rule")
    expect(outcome.sent).toBe(true)
    assertPlain(channel.sent)
    expect(channel.sent.join("\n")).toContain("/new")
  })

  it("replays /new and confirms the created task", async () => {
    const tasks = fakeTasks()
    const channel = fakeChannel()
    const outcome = await handleButlerInbound({
      butler: new ButlerRuntime({ model: fakeModel(), tasks, clock }),
      channel,
      recipient,
      input: {
        conversationId: "c1",
        userId: "user-1",
        projectId: "p1",
        content: "/new 修复登录超时",
      },
    })

    expect(outcome.result.route).toBe("rule")
    expect(tasks.approvals).toHaveLength(0)
    assertPlain(channel.sent)
    expect(channel.sent.join("\n")).toContain("任务")
    expect(channel.sent.join("\n")).not.toMatch(/\b(write|bash|edit)\b/)
  })

  it("falls back to a readable message when the model returns nothing", async () => {
    const channel = fakeChannel()
    const outcome = await handleButlerInbound({
      butler: new ButlerRuntime({ model: fakeModel([{ content: "   " }]), clock }),
      channel,
      recipient,
      input: { conversationId: "c1", userId: "user-1", content: "在吗" },
    })

    expect(outcome.sent).toBe(true)
    assertPlain(channel.sent)
    expect(channel.sent[0]).toContain("我先记下了")
  })

  it("explains a stale approval instead of failing silently", async () => {
    const channel = fakeChannel()
    const outcome = await handleButlerInbound({
      butler: new ButlerRuntime({ model: fakeModel(), tasks: fakeTasks(), clock }),
      channel,
      recipient,
      input: {
        conversationId: "c1",
        userId: "user-1",
        projectId: "p1",
        content: "",
        approvalPayload: "approve:task-404",
      },
    })

    expect(outcome.sent).toBe(true)
    expect(channel.sent[0]).toContain("没有找到任务")
  })
})

describe("detached task notifications", () => {
  it("formats settled tasks with a short id and a readable result", () => {
    const done = formatTaskSettledNotice({
      taskId: "task-123456789",
      projectId: "p1",
      status: "idle",
      summary: "补一版 README",
      lastReply: "已完成并提交",
    })
    expect(done).toContain("【任务完成】task-123")
    expect(done).toContain("补一版 README")
    expect(done).toContain("结果：已完成并提交")

    const failed = formatTaskSettledNotice({
      taskId: "task-987654321",
      projectId: "p1",
      status: "failed",
      summary: "修登录",
      error: "测试未通过",
    })
    expect(failed).toContain("【任务失败】task-987")
    expect(failed).toContain("原因：测试未通过")

    expect(
      formatTaskSettledNotice({
        taskId: "task-1",
        projectId: "p1",
        status: "paused",
        summary: "等待审批",
      }),
    ).toBe("")
  })

  it("pushes exactly one completion notice to the conversation owner", async () => {
    const pushes: { to: string; text: string }[] = []
    const notify = createTaskSettledNotifier({
      approvalNotice: async () => null,
      resolveOwner: (conversationId) => (conversationId === "c1" ? "user-1" : undefined),
      push: async (input) => {
        pushes.push(input)
        return { ok: true }
      },
    })

    await notify({
      taskId: "task-1",
      projectId: "p1",
      conversationId: "c1",
      status: "idle",
      summary: "补 README",
      lastReply: "已完成",
    })

    expect(pushes).toHaveLength(1)
    expect(pushes[0]?.to).toBe("user-1")
    expect(pushes[0]?.text).toContain("【任务完成】")
  })

  it("pushes the approval notice when the task pauses", async () => {
    const pushes: { to: string; text: string }[] = []
    let noticeFor = ""
    const notify = createTaskSettledNotifier({
      approvalNotice: async (taskId) => {
        noticeFor = taskId
        return { text: "任务 task-1 需要确认" }
      },
      resolveOwner: () => "user-1",
      push: async (input) => {
        pushes.push(input)
        return { ok: true }
      },
    })

    await notify({
      taskId: "task-1",
      projectId: "p1",
      conversationId: "c1",
      status: "paused",
      summary: "等待审批",
    })

    expect(noticeFor).toBe("task-1")
    expect(pushes).toHaveLength(1)
    expect(pushes[0]?.text).toContain("需要确认")
  })

  it("skips when the conversation has no owner mapping", async () => {
    const pushes: unknown[] = []
    const notify = createTaskSettledNotifier({
      approvalNotice: async () => ({ text: "需要确认" }),
      resolveOwner: () => undefined,
      push: async (input) => {
        pushes.push(input)
        return { ok: true }
      },
    })

    await notify({
      taskId: "task-1",
      projectId: "p1",
      conversationId: "c-missing",
      status: "idle",
    })
    expect(pushes).toHaveLength(0)
  })
})

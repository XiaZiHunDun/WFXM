import { describe, expect, it } from "vitest"
import {
  ButlerRuntime,
  type ButlerModelPort,
  type ButlerModelReply,
} from "@butler/runtime/butler/index.js"
import type { ButlerTaskPort, ButlerTaskRef } from "@butler/ports/core/butler-task.js"
import type { ChannelPort, ChannelRecipient } from "@butler/ports/core/channel.js"
import { handleButlerInbound, notifyApprovalIfPaused } from "./butler-inbound.js"

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

describe("notifyApprovalIfPaused", () => {
  it("pushes the approval prompt for a paused task", async () => {
    const tasks = fakeTasks([
      {
        taskId: "t1",
        projectId: "p1",
        status: "paused",
        summary: "写 a.txt",
        pending: { toolName: "write", reason: "需要审批" },
      },
    ])
    const butler = new ButlerRuntime({ model: fakeModel(), tasks, clock })
    const channel = fakeChannel()

    const outcome = await notifyApprovalIfPaused({
      butler,
      channel,
      recipient,
      taskId: "t1",
    })

    expect(outcome?.sent).toBe(true)
    expect(channel.sent[0]).toContain("任务 t1 需要确认")
    expect(channel.sent[0]).toContain("待执行：修改文件")
  })

  it("does nothing when the task is not paused", async () => {
    const tasks = fakeTasks([{ taskId: "t1", projectId: "p1", status: "idle" }])
    const butler = new ButlerRuntime({ model: fakeModel(), tasks, clock })
    const channel = fakeChannel()

    const outcome = await notifyApprovalIfPaused({ butler, channel, recipient, taskId: "t1" })
    expect(outcome).toBeNull()
    expect(channel.sent).toHaveLength(0)
  })
})

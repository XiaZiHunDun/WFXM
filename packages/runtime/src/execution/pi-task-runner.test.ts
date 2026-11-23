import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import type { AgentMessage, AgentTool, StreamFn } from "@butler/pi-agent"
import {
  createAssistantMessageEventStream,
  type AssistantMessage,
  type Model,
} from "@earendil-works/pi-ai"
import {
  bashNeedsApproval,
  createDefaultApprovalPolicy,
  GlobalAgentLock,
  MemoryPiTaskSessionStore,
  PiTaskBusyError,
  PiTaskRunner,
  type PiApprovalPolicy,
} from "./pi-task-runner.js"

const MODEL: Model<"openai-completions"> = {
  id: "fake",
  name: "fake",
  api: "openai-completions",
  provider: "fake",
  baseUrl: "http://127.0.0.1",
  input: ["text"],
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
  contextWindow: 128_000,
  maxTokens: 4_096,
  reasoning: false,
}

const USAGE: AssistantMessage["usage"] = {
  input: 1,
  output: 1,
  cacheRead: 0,
  cacheWrite: 0,
  totalTokens: 2,
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
}

interface Step {
  readonly text?: string
  readonly tools?: readonly { id: string; name: string; args: Record<string, unknown> }[]
}

function assistant(step: Step): AssistantMessage {
  const content: AssistantMessage["content"] = []
  if (step.text) content.push({ type: "text", text: step.text })
  for (const tool of step.tools ?? []) {
    content.push({ type: "toolCall", id: tool.id, name: tool.name, arguments: tool.args })
  }
  return {
    role: "assistant",
    content,
    api: "openai-completions",
    provider: "fake",
    model: "fake",
    usage: USAGE,
    stopReason: step.tools?.length ? "toolUse" : "stop",
    timestamp: Date.now(),
  }
}

function scriptedStream(steps: readonly Step[]): StreamFn {
  let index = 0
  return () => {
    const step = steps[Math.min(index, steps.length - 1)] ?? { text: "done" }
    index += 1
    const message = assistant(step)
    const stream = createAssistantMessageEventStream()
    stream.push({ type: "start", partial: message })
    if (step.text) {
      stream.push({ type: "text_start", contentIndex: 0, partial: message })
      stream.push({ type: "text_delta", contentIndex: 0, delta: step.text, partial: message })
      stream.push({ type: "text_end", contentIndex: 0, content: step.text, partial: message })
    }
    stream.push({
      type: "done",
      reason: step.tools?.length ? "toolUse" : "stop",
      message,
    })
    return stream
  }
}

const autoApprove: PiApprovalPolicy = { check: () => ({ required: false }) }

let root: string

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "pi-runner-"))
})

afterEach(() => {
  rmSync(root, { recursive: true, force: true })
})

function runner(
  streamFn: StreamFn,
  extra: Partial<ConstructorParameters<typeof PiTaskRunner>[0]> = {},
) {
  return new PiTaskRunner({
    model: MODEL,
    apiKey: "fake",
    streamFn,
    approvalPolicy: autoApprove,
    ...extra,
  })
}

async function openTask(run: PiTaskRunner, taskId = "t1"): Promise<void> {
  await run.open({ taskId, projectId: "p1", cwd: root })
}

describe("PiTaskRunner", () => {
  it("only requires approval for destructive bash commands", () => {
    expect(bashNeedsApproval("find . -name legacy.mjs -print -delete")).toBe(true)
    expect(bashNeedsApproval("echo hi >> README.md")).toBe(true)
    expect(bashNeedsApproval("rm -rf src")).toBe(true)
    expect(bashNeedsApproval("node --test test/a.test.mjs")).toBe(false)
    expect(bashNeedsApproval("grep -rn needle . 2>/dev/null")).toBe(false)
  })
  it("runs a read task and normalizes tool names", async () => {
    writeFileSync(join(root, "a.txt"), "hello runner\n")
    const run = runner(
      scriptedStream([
        { tools: [{ id: "c1", name: "read", args: { path: "a.txt" } }] },
        { text: "读到了 hello" },
      ]),
    )
    await openTask(run)
    const result = await run.start("t1", "读一下 a.txt")
    expect(result.status).toBe("idle")
    expect(result.reply).toContain("读到了")
    expect(result.toolCalls).toHaveLength(1)
    expect(result.toolCalls[0]).toMatchObject({
      rawName: "read",
      normalizedName: "read_file",
      ok: true,
    })
    expect(result.toolCalls[0]?.output).toContain("hello runner")
  })

  it("executes a write when approval is not required", async () => {
    const run = runner(
      scriptedStream([
        { tools: [{ id: "c1", name: "write", args: { path: "b.txt", content: "written" } }] },
        { text: "已写入" },
      ]),
    )
    await openTask(run)
    const result = await run.start("t1", "写 b.txt")
    expect(result.status).toBe("idle")
    expect(readFileSync(join(root, "b.txt"), "utf8")).toBe("written")
  })

  it("runs a bash task", async () => {
    const run = runner(
      scriptedStream([
        { tools: [{ id: "c1", name: "bash", args: { command: "echo bash-ok" } }] },
        { text: "命令完成" },
      ]),
    )
    await openTask(run)
    const result = await run.start("t1", "跑个命令")
    expect(result.toolCalls[0]).toMatchObject({
      rawName: "bash",
      normalizedName: "run_command",
      ok: true,
    })
    expect(result.toolCalls[0]?.output).toContain("bash-ok")
  })

  it("reports a finished turn to the memory port", async () => {
    writeFileSync(
      join(root, "x.test.mjs"),
      "import { test } from 'node:test'\ntest('ok', () => {})\n",
    )
    const events: unknown[] = []
    const run = runner(
      scriptedStream([
        {
          tools: [
            { id: "c1", name: "write", args: { path: "d.txt", content: "x" } },
            { id: "c2", name: "bash", args: { command: "node --test x.test.mjs" } },
          ],
        },
        { text: "已完成" },
      ]),
      { memory: { recordTaskOutcome: async (event) => void events.push(event) } },
    )
    await openTask(run)
    const result = await run.start("t1", "改 d.txt 并跑测试")
    expect(result.status).toBe("idle")
    expect(events).toHaveLength(1)
    expect(events[0]).toMatchObject({
      taskId: "t1",
      projectId: "p1",
      goal: "改 d.txt 并跑测试",
      summary: "已完成",
      status: "completed",
      changedFiles: ["d.txt"],
      tests: { command: "node --test x.test.mjs", passed: true },
    })
  })

  it("does not report a paused turn to the memory port", async () => {
    const events: unknown[] = []
    const run = runner(
      scriptedStream([
        { tools: [{ id: "c1", name: "write", args: { path: "e.txt", content: "x" } }] },
        { text: "写入完成" },
      ]),
      {
        approvalPolicy: createDefaultApprovalPolicy({ BUTLER_V5_PI_APPROVAL: "always" }),
        memory: { recordTaskOutcome: async (event) => void events.push(event) },
      },
    )
    await openTask(run)
    const paused = await run.start("t1", "写 e.txt")
    expect(paused.status).toBe("paused")
    expect(events).toHaveLength(0)
  })

  it("pauses on approval and writes after approval", async () => {
    const run = runner(
      scriptedStream([
        { tools: [{ id: "c1", name: "write", args: { path: "c.txt", content: "approved" } }] },
        { text: "写入完成" },
      ]),
      { approvalPolicy: createDefaultApprovalPolicy({ BUTLER_V5_PI_APPROVAL: "always" }) },
    )
    await openTask(run)
    const paused = await run.start("t1", "写 c.txt")
    expect(paused.status).toBe("paused")
    expect(paused.pendingStep?.toolName).toBe("write")
    expect(() => readFileSync(join(root, "c.txt"), "utf8")).toThrow()

    const resumed = await run.resume("t1", { approved: true })
    expect(resumed.status).toBe("idle")
    expect(resumed.pendingStep).toBeNull()
    expect(readFileSync(join(root, "c.txt"), "utf8")).toBe("approved")
  })

  it("keeps the file untouched when approval is denied", async () => {
    const run = runner(
      scriptedStream([
        { tools: [{ id: "c1", name: "write", args: { path: "d.txt", content: "denied" } }] },
        { text: "已取消" },
      ]),
      { approvalPolicy: createDefaultApprovalPolicy({ BUTLER_V5_PI_APPROVAL: "always" }) },
    )
    await openTask(run)
    await run.start("t1", "写 d.txt")
    const resumed = await run.resume("t1", { approved: false, note: "不要写" })
    expect(resumed.status).toBe("idle")
    expect(() => readFileSync(join(root, "d.txt"), "utf8")).toThrow()
    const record = await run.load("t1")
    expect(JSON.stringify(record?.snapshot.messages)).toContain("用户拒绝执行该操作")
  })

  it("stops a batch at the first approval and fills in the skipped calls", async () => {
    const run = runner(
      scriptedStream([
        {
          tools: [
            { id: "c1", name: "write", args: { path: "e.txt", content: "approved" } },
            { id: "c2", name: "bash", args: { command: "echo skipped > later.txt" } },
          ],
        },
        { text: "写入完成" },
        { text: "写入完成" },
      ]),
      { approvalPolicy: createDefaultApprovalPolicy({}) },
    )
    await openTask(run)

    const paused = await run.start("t1", "写 e.txt 并追加")
    expect(paused.status).toBe("paused")
    expect(paused.pendingStep).toMatchObject({ toolCallId: "c1", toolName: "write" })
    expect(paused.toolCalls).toHaveLength(0)
    expect(() => readFileSync(join(root, "e.txt"), "utf8")).toThrow()
    expect(() => readFileSync(join(root, "later.txt"), "utf8")).toThrow()

    const resumed = await run.resume("t1", { approved: true })
    expect(resumed.status).toBe("idle")
    expect(readFileSync(join(root, "e.txt"), "utf8")).toBe("approved")
    // The second call in the same batch must not run without its own approval.
    expect(() => readFileSync(join(root, "later.txt"), "utf8")).toThrow()

    const record = await run.load("t1")
    expect(JSON.stringify(record?.snapshot.messages)).toContain("等待审批，本步未执行")
  })

  it("serializes concurrent tasks with the global lock", async () => {
    let release!: () => void
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    const calls: string[] = []
    const streamFn: StreamFn = () => {
      calls.push(calls.length === 0 ? "first" : "second")
      if (calls.length === 1) {
        return gate.then(() => scriptedStream([{ text: "first done" }])())
      }
      return scriptedStream([{ text: "second done" }])()
    }
    const lock = new GlobalAgentLock()
    const run = runner(streamFn, { lock })
    await run.open({ taskId: "a", projectId: "p", cwd: root })
    await run.open({ taskId: "b", projectId: "p", cwd: root })

    const first = run.start("a", "first")
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(calls).toEqual(["first"])
    const second = run.start("b", "second")
    await new Promise((resolve) => setTimeout(resolve, 20))
    // Observable serialization: the second task must not start streaming
    // before the first one finishes.
    expect(calls).toEqual(["first"])

    release()
    const [a, b] = await Promise.all([first, second])
    expect(calls).toEqual(["first", "second"])
    expect(a.reply).toContain("first done")
    expect(b.reply).toContain("second done")
  })

  it("restores a session snapshot in another runner", async () => {
    const store = new MemoryPiTaskSessionStore()
    const first = runner(
      scriptedStream([
        { tools: [{ id: "c1", name: "read", args: { path: "a.txt" } }] },
        { text: "第一轮完成" },
      ]),
      { store },
    )
    writeFileSync(join(root, "a.txt"), "history\n")
    await first.open({ taskId: "t1", projectId: "p1", cwd: root })
    await first.start("t1", "第一轮")

    const second = runner(scriptedStream([{ text: "第二轮完成" }]), { store })
    await second.load("t1")
    const result = await second.start("t1", "第二轮")
    expect(result.reply).toContain("第二轮完成")

    const record = await store.load("t1")
    const roles = (record?.snapshot.messages as AgentMessage[]).map((message) => message.role)
    expect(roles.filter((role) => role === "user")).toHaveLength(2)
  })

  it("blocks tool calls past the budget", async () => {
    const run = runner(
      scriptedStream([
        { tools: [{ id: "c1", name: "read", args: { path: "a.txt" } }] },
        { tools: [{ id: "c2", name: "read", args: { path: "a.txt" } }] },
        { text: "结束" },
      ]),
      { maxToolCalls: 1 },
    )
    writeFileSync(join(root, "a.txt"), "x\n")
    await openTask(run)
    const result = await run.start("t1", "读两次")
    expect(result.toolCalls).toHaveLength(1)
    expect(result.status).toBe("idle")
  })

  it("rejects start on a paused session", async () => {
    const run = runner(
      scriptedStream([
        { tools: [{ id: "c1", name: "write", args: { path: "e.txt", content: "x" } }] },
      ]),
      { approvalPolicy: createDefaultApprovalPolicy({ BUTLER_V5_PI_APPROVAL: "always" }) },
    )
    await openTask(run)
    await run.start("t1", "写")
    await expect(run.start("t1", "再写")).rejects.toThrow(/paused/)
  })

  describe("task contract", () => {
    it("rejects start and resume for an unknown task", async () => {
      const run = runner(scriptedStream([{ text: "noop" }]))
      await expect(run.start("missing", "hi")).rejects.toThrow(/not found/)
      await expect(run.resume("missing", { approved: true })).rejects.toThrow(/not found/)
    })

    it("rejects open when cwd is not a directory", async () => {
      const run = runner(scriptedStream([{ text: "noop" }]))
      await expect(
        run.open({ taskId: "t1", projectId: "p1", cwd: join(root, "missing-dir") }),
      ).rejects.toThrow(/cannot open task/)
    })

    it("rejects resume on a task that is not paused without side effects", async () => {
      const run = runner(scriptedStream([{ text: "完成" }]))
      await openTask(run)
      await run.start("t1", "hi")

      const before = await run.load("t1")
      await expect(run.resume("t1", { approved: true })).rejects.toThrow(/not paused/)
      const after = await run.load("t1")

      expect(after?.status).toBe("idle")
      expect(after?.snapshot.messages).toEqual(before?.snapshot.messages)
    })

    it("continues a soft-paused task without an approval prompt", async () => {
      let sawApprovalPrompt = false
      const streamFn: StreamFn = (_model, context) => {
        if (JSON.stringify(context).includes("审批已通过")) sawApprovalPrompt = true
        return scriptedStream([{ text: "继续完成" }])()
      }
      const run = runner(streamFn)
      await openTask(run)
      await run.pause("t1")
      expect((await run.load("t1"))?.status).toBe("paused")

      const result = await run.resume("t1", { approved: true })
      expect(result.status).toBe("idle")
      expect(result.reply).toContain("继续完成")
      expect(sawApprovalPrompt).toBe(false)
    })

    it("rejects a second turn on the same task while the first is running", async () => {
      let release!: () => void
      const gate = new Promise<void>((resolve) => {
        release = resolve
      })
      const streamFn: StreamFn = () => gate.then(() => scriptedStream([{ text: "done" }])())
      const run = runner(streamFn)
      await openTask(run)

      const first = run.start("t1", "first")
      await new Promise((resolve) => setTimeout(resolve, 10))
      await expect(run.start("t1", "second")).rejects.toThrow(PiTaskBusyError)

      release()
      const result = await first
      expect(result.reply).toContain("done")
    })

    it("reports a reason when the tool budget ends the turn", async () => {
      writeFileSync(join(root, "a.txt"), "x\n")
      const run = runner(
        scriptedStream([{ tools: [{ id: "c1", name: "read", args: { path: "a.txt" } }] }]),
        { maxToolCalls: 0 },
      )
      await openTask(run)

      const result = await run.start("t1", "读 a.txt")
      expect(result.status).toBe("idle")
      expect(result.reply).toMatch(/额度/)
    })

    it("surfaces a model error as the turn reply", async () => {
      const streamFn: StreamFn = () => {
        const stream = createAssistantMessageEventStream()
        stream.push({
          type: "error",
          reason: "error",
          error: { ...assistant({}), stopReason: "error", errorMessage: "模型不可用" },
        })
        return stream
      }
      const run = runner(streamFn)
      await openTask(run)

      const result = await run.start("t1", "hi")
      expect(result.status).toBe("failed")
      expect(result.reply).toContain("模型不可用")
    })

    it("does not drive a closed task", async () => {
      const run = runner(scriptedStream([{ text: "完成" }]))
      await openTask(run)
      await run.close("t1")

      await expect(run.start("t1", "again")).rejects.toThrow(/not found/)
      await expect(run.resume("t1", { approved: true })).rejects.toThrow(/not found/)
    })
  })

  describe("transcript integrity", () => {
    it("rejects an unsupported snapshot version", async () => {
      const store = new MemoryPiTaskSessionStore()
      const first = runner(scriptedStream([{ text: "ok" }]), { store })
      await openTask(first)
      const record = await store.load("t1")
      if (!record) throw new Error("t1 not found")
      await store.save({
        ...record,
        snapshot: { ...record.snapshot, version: 2 as unknown as 1 },
      })

      const second = runner(scriptedStream([{ text: "ok" }]), { store })
      await expect(second.start("t1", "hi")).rejects.toThrow(/unsupported session snapshot version/)
    })

    it("rejects a snapshot that does not start with a system message", async () => {
      const store = new MemoryPiTaskSessionStore()
      const first = runner(scriptedStream([{ text: "ok" }]), { store })
      await openTask(first)
      const record = await store.load("t1")
      if (!record) throw new Error("t1 not found")
      await store.save({
        ...record,
        snapshot: {
          ...record.snapshot,
          messages: [{ role: "user", content: [{ type: "text", text: "hi" }] }],
        },
      })

      const second = runner(scriptedStream([{ text: "ok" }]), { store })
      await expect(second.start("t1", "hi")).rejects.toThrow(/first message must be a system/)
    })

    it("rejects a snapshot with duplicate system messages", async () => {
      const store = new MemoryPiTaskSessionStore()
      const first = runner(scriptedStream([{ text: "ok" }]), { store })
      await openTask(first)
      const record = await store.load("t1")
      if (!record) throw new Error("t1 not found")
      await store.save({
        ...record,
        snapshot: {
          ...record.snapshot,
          messages: [{ role: "system" }, { role: "system" }],
        },
      })

      const second = runner(scriptedStream([{ text: "ok" }]), { store })
      await expect(second.start("t1", "hi")).rejects.toThrow(/system messages/)
    })

    it("keeps exactly one leading system message across runners", async () => {
      const store = new MemoryPiTaskSessionStore()
      const first = runner(scriptedStream([{ text: "第一轮" }]), { store })
      await openTask(first)
      await first.start("t1", "hi")

      let systemCount = -1
      const streamFn: StreamFn = (_model, context) => {
        const messages = (context as { messages?: { role?: string }[] }).messages ?? []
        systemCount = messages.filter((message) => message.role === "system").length
        return scriptedStream([{ text: "第二轮" }])()
      }
      const second = runner(streamFn, { store })
      await second.start("t1", "again")

      expect(systemCount).toBe(1)
      const record = await store.load("t1")
      const roles = (record?.snapshot.messages ?? []).map(
        (message) => (message as { role: string }).role,
      )
      expect(roles.filter((role) => role === "system")).toHaveLength(1)
      expect(roles[0]).toBe("system")
    })

    it("pairs every tool call and does not execute deferred calls", async () => {
      const approval: PiApprovalPolicy = {
        check: () => ({ required: true, reason: "需要确认" }),
      }
      const run = runner(
        scriptedStream([
          {
            tools: [
              { id: "c1", name: "write", args: { path: "a.txt", content: "a" } },
              { id: "c2", name: "write", args: { path: "b.txt", content: "b" } },
            ],
          },
          { text: "完成" },
        ]),
        { approvalPolicy: approval },
      )
      await openTask(run)

      const paused = await run.start("t1", "写两个文件")
      expect(paused.status).toBe("paused")
      expect(paused.reply).toBe("需要确认")
      expect(existsSync(join(root, "a.txt"))).toBe(false)

      const record = await run.load("t1")
      const messages = record?.snapshot.messages ?? []
      const assistant = [...messages]
        .reverse()
        .find(
          (message) =>
            (message as { role: string }).role === "assistant" &&
            Array.isArray((message as { content?: unknown }).content),
        ) as { content: { type: string; id?: string }[] }
      const callIds = assistant.content
        .filter((block) => block.type === "toolCall")
        .map((block) => block.id)
      const resultIds = messages
        .filter((message) => (message as { role: string }).role === "toolResult")
        .map((message) => (message as { toolCallId: string }).toolCallId)
      expect(resultIds.sort()).toEqual(callIds.sort())

      const deferred = messages.find(
        (message) => (message as { toolCallId?: string }).toolCallId === "c2",
      ) as { content: { text: string }[] }
      expect(deferred.content[0]?.text).toContain("未执行")

      const resumed = await run.resume("t1", { approved: true })
      expect(resumed.status).toBe("idle")
      expect(existsSync(join(root, "a.txt"))).toBe(true)
      expect(existsSync(join(root, "b.txt"))).toBe(false)
    })

    it("repairs a dangling tool result left by an interrupted batch", async () => {
      const store = new MemoryPiTaskSessionStore()
      const approval: PiApprovalPolicy = {
        check: () => ({ required: true, reason: "需要确认" }),
      }
      const first = runner(
        scriptedStream([
          {
            tools: [
              { id: "c1", name: "write", args: { path: "a.txt", content: "a" } },
              { id: "c2", name: "write", args: { path: "b.txt", content: "b" } },
            ],
          },
        ]),
        { store, approvalPolicy: approval },
      )
      await openTask(first)
      await first.start("t1", "写两个文件")

      const record = await store.load("t1")
      if (!record) throw new Error("t1 not found")
      await store.save({
        ...record,
        snapshot: {
          ...record.snapshot,
          messages: record.snapshot.messages.filter(
            (message) => (message as { toolCallId?: string }).toolCallId !== "c2",
          ),
        },
      })

      let sawRepair = false
      const streamFn: StreamFn = (_model, context) => {
        sawRepair = JSON.stringify(context).includes("未执行")
        return scriptedStream([{ text: "已取消" }])()
      }
      const second = runner(streamFn, { store, approvalPolicy: approval })
      const result = await second.resume("t1", { approved: false })

      expect(result.status).toBe("idle")
      expect(sawRepair).toBe(true)
      expect(existsSync(join(root, "b.txt"))).toBe(false)
    })

    it("completes calls skipped by an abort mid-batch", async () => {
      const holder: { run: PiTaskRunner | null } = { run: null }
      const pauseTool = {
        name: "read",
        label: "read",
        description: "pause the current task",
        parameters: { type: "object", properties: {}, additionalProperties: true },
        execute: async () => {
          if (!holder.run) throw new Error("runner not ready")
          await holder.run.pause("t1")
          return { content: [{ type: "text", text: "paused" }], details: undefined }
        },
      } as unknown as AgentTool
      const run = runner(
        scriptedStream([
          {
            tools: [
              { id: "c1", name: "read", args: {} },
              { id: "c2", name: "read", args: {} },
            ],
          },
          { text: "已暂停" },
        ]),
        { tools: [pauseTool] },
      )
      holder.run = run
      await openTask(run)

      const result = await run.start("t1", "读两个")
      expect(result.status).toBe("paused")

      const record = await run.load("t1")
      const resultIds = (record?.snapshot.messages ?? [])
        .filter((message) => (message as { role: string }).role === "toolResult")
        .map((message) => (message as { toolCallId: string }).toolCallId)
      expect(resultIds).toEqual(expect.arrayContaining(["c1", "c2"]))
    })
  })

  describe("tool protocol", () => {
    it("continues after a tool returns an error result", async () => {
      const run = runner(
        scriptedStream([
          { tools: [{ id: "c1", name: "read", args: { path: "missing.txt" } }] },
          { text: "文件不存在，还需要我做什么？" },
        ]),
      )
      await openTask(run)

      const result = await run.start("t1", "读 missing.txt")
      expect(result.status).toBe("idle")
      expect(result.reply).toContain("文件不存在")
      expect(result.toolCalls).toHaveLength(1)
      expect(result.toolCalls[0]?.ok).toBe(false)
    })

    it("normalizes names for reporting without changing approval or execution", async () => {
      const seen: string[] = []
      const policy: PiApprovalPolicy = {
        check: ({ toolName }) => {
          seen.push(toolName)
          return toolName === "write" ? { required: true, reason: "需要确认" } : { required: false }
        },
      }
      const run = runner(
        scriptedStream([
          { tools: [{ id: "c1", name: "write", args: { path: "a.txt", content: "a" } }] },
          { text: "完成" },
        ]),
        { approvalPolicy: policy },
      )
      await openTask(run)

      const paused = await run.start("t1", "写 a.txt")
      expect(paused.status).toBe("paused")
      expect(seen).toEqual(["write"])
      expect(paused.pendingStep?.toolName).toBe("write")
      expect(existsSync(join(root, "a.txt"))).toBe(false)

      const resumed = await run.resume("t1", { approved: true })
      expect(resumed.status).toBe("idle")
      expect(resumed.toolCalls[0]?.rawName).toBe("write")
      expect(resumed.toolCalls[0]?.normalizedName).toBe("write_file")
      expect(readFileSync(join(root, "a.txt"), "utf8")).toBe("a")
    })
  })

  describe("approval gate", () => {
    const alwaysApprove: PiApprovalPolicy = {
      check: () => ({ required: true, reason: "需要确认" }),
    }

    function countingWriteTool(counter: { runs: number }): AgentTool {
      return {
        name: "write",
        label: "write",
        description: "count write executions",
        parameters: { type: "object", properties: {}, additionalProperties: true },
        execute: async () => {
          counter.runs += 1
          return { content: [{ type: "text", text: "ok" }], details: undefined }
        },
      } as unknown as AgentTool
    }

    async function pausedTask(store: MemoryPiTaskSessionStore, counter: { runs: number }) {
      const run = runner(
        scriptedStream([
          { tools: [{ id: "c1", name: "write", args: { path: "a.txt", content: "a" } }] },
        ]),
        { store, approvalPolicy: alwaysApprove, tools: [countingWriteTool(counter)] },
      )
      await openTask(run)
      const paused = await run.start("t1", "写 a.txt")
      expect(paused.status).toBe("paused")
      return run
    }

    it("requires approval for write/edit and destructive bash only", async () => {
      const policy = createDefaultApprovalPolicy({})
      expect(await policy.check({ toolName: "write", args: {}, cwd: root })).toMatchObject({
        required: true,
      })
      expect(await policy.check({ toolName: "edit", args: {}, cwd: root })).toMatchObject({
        required: true,
      })
      expect(
        await policy.check({ toolName: "bash", args: { command: "ls -la" }, cwd: root }),
      ).toEqual({ required: false })
      expect(
        await policy.check({ toolName: "bash", args: { command: "rm -rf src" }, cwd: root }),
      ).toMatchObject({ required: true })
      expect(await policy.check({ toolName: "read", args: { path: "a" }, cwd: root })).toEqual({
        required: false,
      })
    })

    it("does not execute or retry a denied step", async () => {
      const counter = { runs: 0 }
      const run = runner(
        scriptedStream([
          { tools: [{ id: "c1", name: "write", args: { path: "a.txt", content: "a" } }] },
          { text: "已取消" },
        ]),
        { approvalPolicy: alwaysApprove, tools: [countingWriteTool(counter)] },
      )
      await openTask(run)
      await run.start("t1", "写 a.txt")

      const denied = await run.resume("t1", { approved: false, note: "不要写" })
      expect(counter.runs).toBe(0)
      expect(denied.toolCalls).toHaveLength(0)
      expect(denied.reply).toContain("已取消")
      expect((await run.load("t1"))?.pendingStep).toBeNull()
      expect(JSON.stringify((await run.load("t1"))?.snapshot.messages)).toContain("用户拒绝执行")
    })

    it("executes a pending step only once across runners", async () => {
      const store = new MemoryPiTaskSessionStore()
      const counter = { runs: 0 }
      const first = await pausedTask(store, counter)

      const second = runner(scriptedStream([{ text: "完成" }]), {
        store,
        approvalPolicy: alwaysApprove,
        tools: [countingWriteTool(counter)],
      })
      await second.load("t1")
      const resumed = await second.resume("t1", { approved: true })
      expect(resumed.status).toBe("idle")
      expect(counter.runs).toBe(1)

      await expect(first.resume("t1", { approved: true })).rejects.toThrow(/not paused/)
      expect(counter.runs).toBe(1)
    })

    it("does not run a pending step already claimed by another process", async () => {
      const store = new MemoryPiTaskSessionStore()
      const counter = { runs: 0 }
      await pausedTask(store, counter)

      const record = await store.load("t1")
      if (!record?.pendingStep) throw new Error("expected a pending step")
      await store.save({
        ...record,
        pendingStep: { ...record.pendingStep, decidedAt: new Date().toISOString() },
      })

      const second = runner(scriptedStream([{ text: "完成" }]), {
        store,
        approvalPolicy: alwaysApprove,
        tools: [countingWriteTool(counter)],
      })
      const result = await second.resume("t1", { approved: true })

      expect(counter.runs).toBe(0)
      expect(result.reply).toContain("已处理")
      expect((await second.load("t1"))?.pendingStep).toBeNull()
    })

    it("rejects an expired approval instead of hanging", async () => {
      const store = new MemoryPiTaskSessionStore()
      const counter = { runs: 0 }
      await pausedTask(store, counter)

      const record = await store.load("t1")
      if (!record?.pendingStep) throw new Error("expected a pending step")
      await store.save({
        ...record,
        pendingStep: {
          ...record.pendingStep,
          requestedAt: new Date(Date.now() - 60 * 60_000).toISOString(),
        },
      })

      const second = runner(scriptedStream([{ text: "完成" }]), {
        store,
        approvalPolicy: alwaysApprove,
        tools: [countingWriteTool(counter)],
      })
      const result = await second.resume("t1", { approved: true })

      expect(counter.runs).toBe(0)
      expect(result.reply).toContain("过期")
      expect((await second.load("t1"))?.pendingStep).toBeNull()
      expect((await second.load("t1"))?.snapshot.lastReply).toContain("过期")
    })
  })

  describe("persistence lifecycle", () => {
    it("resumes a saved transcript with a second runner", async () => {
      const store = new MemoryPiTaskSessionStore()
      const first = runner(scriptedStream([{ text: "第一轮" }]), { store })
      await openTask(first)
      await first.start("t1", "hi")

      const second = runner(scriptedStream([{ text: "第二轮" }]), { store })
      const result = await second.start("t1", "again")
      expect(result.reply).toContain("第二轮")

      const saved = JSON.stringify((await store.load("t1"))?.snapshot.messages)
      expect(saved).toContain("第一轮")
      expect(saved).toContain("第二轮")
    })

    it("closes a task and releases its record", async () => {
      const store = new MemoryPiTaskSessionStore()
      const run = runner(scriptedStream([{ text: "完成" }]), { store })
      await openTask(run)
      await run.start("t1", "hi")

      await run.close("t1")
      expect(await run.load("t1")).toBeNull()
      expect(await store.load("t1")).toBeNull()

      const other = runner(scriptedStream([{ text: "完成" }]), { store })
      expect(await other.load("t1")).toBeNull()
      await expect(other.start("t1", "hi")).rejects.toThrow(/not found/)
      await expect(run.close("t1")).resolves.toBeUndefined()
    })

    it("does not resurrect a task closed mid-turn", async () => {
      const store = new MemoryPiTaskSessionStore()
      let release!: () => void
      const gate = new Promise<void>((resolve) => {
        release = resolve
      })
      const streamFn: StreamFn = () => gate.then(() => scriptedStream([{ text: "done" }])())
      const run = runner(streamFn, { store })
      await openTask(run)

      const turn = run.start("t1", "first")
      await new Promise((resolve) => setTimeout(resolve, 10))
      await run.close("t1")
      release()

      const result = await turn
      expect(result.status).toBe("closed")
      expect(result.reply).toContain("已关闭")
      expect(await store.load("t1")).toBeNull()
    })

    it("surfaces store failures with the task id", async () => {
      class FlakyStore extends MemoryPiTaskSessionStore {
        failSave = false
        override async save(
          record: Parameters<MemoryPiTaskSessionStore["save"]>[0],
        ): Promise<void> {
          if (this.failSave) throw new Error("database unavailable")
          return super.save(record)
        }
      }
      const store = new FlakyStore()
      const run = runner(scriptedStream([{ text: "完成" }]), { store })
      await openTask(run)

      store.failSave = true
      await expect(run.start("t1", "hi")).rejects.toThrow(
        /task t1: failed to persist session.*database unavailable/,
      )
    })

    it("rejects a corrupt record without crashing", async () => {
      const store = new MemoryPiTaskSessionStore()
      const first = runner(scriptedStream([{ text: "ok" }]), { store })
      await openTask(first)
      const record = await store.load("t1")
      if (!record) throw new Error("t1 not found")

      await store.save({ ...record, snapshot: null as never })
      const second = runner(scriptedStream([{ text: "ok" }]), { store })
      await expect(second.start("t1", "hi")).rejects.toThrow(/session snapshot is missing/)

      await store.save({
        ...record,
        snapshot: { ...record.snapshot, messages: "oops" as never },
      })
      const third = runner(scriptedStream([{ text: "ok" }]), { store })
      await expect(third.start("t1", "hi")).rejects.toThrow(/messages must be an array/)
    })
  })

  describe("scheduling", () => {
    it("runs queued tasks in FIFO order", async () => {
      let release!: () => void
      const gate = new Promise<void>((resolve) => {
        release = resolve
      })
      const calls: number[] = []
      const streamFn: StreamFn = () => {
        const index = calls.length
        calls.push(index)
        if (index === 0) return gate.then(() => scriptedStream([{ text: "one" }])())
        return scriptedStream([{ text: `reply-${index}` }])()
      }
      const lock = new GlobalAgentLock()
      const run = runner(streamFn, { lock })
      for (const taskId of ["a", "b", "c"]) {
        await run.open({ taskId, projectId: "p", cwd: root })
      }

      const a = run.start("a", "first")
      await new Promise((resolve) => setTimeout(resolve, 20))
      const b = run.start("b", "second")
      await new Promise((resolve) => setTimeout(resolve, 0))
      const c = run.start("c", "third")
      await new Promise((resolve) => setTimeout(resolve, 20))
      expect(calls).toEqual([0])

      release()
      const [ra, rb, rc] = await Promise.all([a, b, c])
      expect(calls).toEqual([0, 1, 2])
      expect(ra.reply).toContain("one")
      expect(rb.reply).toContain("reply-1")
      expect(rc.reply).toContain("reply-2")
    })

    it("releases the lock after a callback throws", async () => {
      const lock = new GlobalAgentLock()
      await expect(
        lock.run("a", async () => {
          throw new Error("boom")
        }),
      ).rejects.toThrow("boom")
      await expect(lock.run("b", async () => "ok")).resolves.toBe("ok")
    })

    it("does not run a task closed while waiting for the lock", async () => {
      let release!: () => void
      const gate = new Promise<void>((resolve) => {
        release = resolve
      })
      const lock = new GlobalAgentLock()
      const blocking = runner(() => gate.then(() => scriptedStream([{ text: "a done" }])()), {
        lock,
      })
      let queuedCalls = 0
      const queued = runner(
        () => {
          queuedCalls += 1
          return scriptedStream([{ text: "b done" }])()
        },
        { lock },
      )
      const following = runner(scriptedStream([{ text: "c done" }]), { lock })
      for (const [target, taskId] of [
        [blocking, "a"],
        [queued, "b"],
        [following, "c"],
      ] as const) {
        await target.open({ taskId, projectId: "p", cwd: root })
      }

      const a = blocking.start("a", "first")
      await new Promise((resolve) => setTimeout(resolve, 20))
      const b = queued.start("b", "second")
      await new Promise((resolve) => setTimeout(resolve, 20))
      expect(queuedCalls).toBe(0)

      await queued.close("b")
      const c = following.start("c", "third")
      release()

      const [aResult, bResult, cResult] = await Promise.allSettled([a, b, c])
      expect(aResult.status).toBe("fulfilled")
      expect(bResult.status).toBe("rejected")
      if (bResult.status === "rejected") expect(String(bResult.reason)).toMatch(/closed/)
      expect(cResult.status).toBe("fulfilled")
      if (cResult.status === "fulfilled") expect(cResult.value.reply).toContain("c done")
      expect(queuedCalls).toBe(0)
    })
  })

  describe("model and context", () => {
    it("marks a timed-out turn as failed with a readable reason", async () => {
      const streamFn: StreamFn = () =>
        new Promise((resolve) => {
          setTimeout(() => resolve(scriptedStream([{ text: "迟到的回复" }])()), 100)
        })
      const run = runner(streamFn)
      await openTask(run)

      const result = await run.start("t1", "hi", { timeoutMs: 10 })
      expect(result.status).toBe("failed")
      expect(result.reply).toMatch(/超时/)
    })

    it("aggregates usage across model calls in one turn", async () => {
      writeFileSync(join(root, "a.txt"), "x")
      const run = runner(
        scriptedStream([
          { tools: [{ id: "c1", name: "read", args: { path: "a.txt" } }] },
          { text: "完成" },
        ]),
      )
      await openTask(run)

      const result = await run.start("t1", "读 a.txt")
      expect(result.usage).toEqual({ inputTokens: 2, outputTokens: 2, totalTokens: 4 })
    })

    it("keeps the turn when the memory projection throws", async () => {
      const store = new MemoryPiTaskSessionStore()
      const run = runner(scriptedStream([{ text: "完成" }]), {
        store,
        memory: {
          recordTaskOutcome: async () => {
            throw new Error("memory down")
          },
        },
      })
      await openTask(run)

      const result = await run.start("t1", "hi")
      expect(result.status).toBe("idle")
      expect(result.reply).toContain("完成")
      expect((await store.load("t1"))?.status).toBe("idle")
    })
  })
})

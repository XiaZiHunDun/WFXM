import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import type { AgentMessage, StreamFn } from "@butler/pi-agent"
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

function runner(streamFn: StreamFn, extra: Partial<ConstructorParameters<typeof PiTaskRunner>[0]> = {}) {
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
    expect(result.toolCalls[0]).toMatchObject({ rawName: "read", normalizedName: "read_file", ok: true })
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
    expect(result.toolCalls[0]).toMatchObject({ rawName: "bash", normalizedName: "run_command", ok: true })
    expect(result.toolCalls[0]?.output).toContain("bash-ok")
  })

  it("reports a finished turn to the memory port", async () => {
    writeFileSync(join(root, "x.test.mjs"), "import { test } from 'node:test'\ntest('ok', () => {})\n")
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
    const second = run.start("b", "second")
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(lock.activeTaskId).toBe("a")
    expect(lock.queueLength).toBe(1)

    release()
    const [a, b] = await Promise.all([first, second])
    expect(a.reply).toContain("first done")
    expect(b.reply).toContain("second done")
    expect(lock.activeTaskId).toBeNull()
    expect(a.reply).toContain("first done")
    expect(b.reply).toContain("second done")
    expect(lock.activeTaskId).toBeNull()
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
})

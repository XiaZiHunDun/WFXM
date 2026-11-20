import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import type { StreamFn } from "@butler/pi-agent"
import {
  createAssistantMessageEventStream,
  type AssistantMessage,
  type Model,
} from "@earendil-works/pi-ai"
import {
  createDefaultApprovalPolicy,
  GlobalAgentLock,
  MemoryPiTaskSessionStore,
  PiTaskRunner,
  type PiApprovalPolicy,
} from "../execution/pi-task-runner.js"
import { createPiTaskPortAdapter, type PiTaskPortAdapterOptions } from "./pi-task-adapter.js"

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
    stream.push({ type: "done", reason: step.tools?.length ? "toolUse" : "stop", message })
    return stream
  }
}

const autoApprove: PiApprovalPolicy = { check: () => ({ required: false }) }

let root: string
let sequence = 0

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "butler-task-adapter-"))
  sequence = 0
})

afterEach(() => {
  rmSync(root, { recursive: true, force: true })
})

function setup(
  streamFn: StreamFn,
  options: {
    readonly approvalPolicy?: PiApprovalPolicy
    readonly detached?: boolean
  } = {},
) {
  const runner = new PiTaskRunner({
    model: MODEL,
    apiKey: "fake",
    streamFn,
    store: new MemoryPiTaskSessionStore(),
    lock: new GlobalAgentLock(),
    approvalPolicy: options.approvalPolicy ?? autoApprove,
  })
  const adapterOptions: PiTaskPortAdapterOptions = {
    resolveCwd: () => root,
    newTaskId: () => `t-${++sequence}`,
    ...(options.detached === undefined ? {} : { detached: options.detached }),
  }
  const adapter = createPiTaskPortAdapter(runner, adapterOptions)
  return { runner, adapter }
}

describe("createPiTaskPortAdapter", () => {
  it("opens a pi task, runs a turn and reports the final status", async () => {
    const { adapter } = setup(
      scriptedStream([
        { tools: [{ id: "c1", name: "write", args: { path: "a.txt", content: "hi" } }] },
        { text: "已写入" },
      ]),
    )
    const ref = await adapter.start({ projectId: "p1", goal: "写 a.txt" })

    expect(ref).toMatchObject({ projectId: "p1", status: "idle", summary: "写 a.txt" })
    expect(ref.lastReply).toContain("已写入")
    expect(readFileSync(join(root, "a.txt"), "utf8")).toBe("hi")

    const status = await adapter.status(ref.taskId)
    expect(status).toMatchObject({ taskId: ref.taskId, status: "idle" })
    expect(status?.lastReply).toContain("已写入")

    const list = await adapter.list("p1")
    expect(list.map((task) => task.taskId)).toContain(ref.taskId)
    expect(await adapter.list("p2")).toHaveLength(0)
    expect(await adapter.status("missing")).toBeNull()
  })

  it("reports the failure reason on the task ref", async () => {
    const { adapter } = setup(() => {
      throw new Error("model down")
    })

    const ref = await adapter.start({ projectId: "p1", goal: "会失败的任务" })
    expect(ref.status).toBe("failed")
    expect(ref.error).toContain("model down")
  })

  it("redacts the workspace path from task results", async () => {
    const { adapter } = setup(scriptedStream([{ text: `已写入 ${root}/a.txt` }]))

    const ref = await adapter.start({ projectId: "p1", goal: "写文件" })
    expect(ref.lastReply).toContain("项目目录")
    expect(ref.lastReply).not.toContain(root)
  })

  it("redacts the workspace path from failure reasons", async () => {
    const { adapter } = setup(() => {
      throw new Error(`boom at ${root}/x`)
    })

    const ref = await adapter.start({ projectId: "p1", goal: "会失败的任务" })
    expect(ref.error).toContain("项目目录")
    expect(ref.error).not.toContain(root)
  })

  it("injects a repository map into the task system prompt", async () => {
    writeFileSync(join(root, "demo.ts"), "export function greet() {}\n")
    const { runner, adapter } = setup(scriptedStream([{ text: "ok" }]))

    const ref = await adapter.start({ projectId: "p1", goal: "看看项目结构" })

    const record = await runner.load(ref.taskId)
    expect(record?.snapshot.systemPrompt).toContain("仓库地图")
    expect(record?.snapshot.systemPrompt).toContain("demo.ts")
    expect(record?.snapshot.systemPrompt).toContain("greet")
  })

  it("forwards approval and resumes the paused task", async () => {
    const { adapter } = setup(
      scriptedStream([
        { tools: [{ id: "c1", name: "write", args: { path: "b.txt", content: "approved" } }] },
        { text: "已写入" },
      ]),
      { approvalPolicy: createDefaultApprovalPolicy({ BUTLER_V5_PI_APPROVAL: "always" }) },
    )

    const paused = await adapter.start({ projectId: "p1", goal: "写 b.txt" })
    expect(paused.status).toBe("paused")
    expect(paused.pending).toMatchObject({ toolName: "write" })
    expect(paused.pending?.reason).toBeTruthy()

    const resumed = await adapter.approve(paused.taskId, true)
    expect(resumed).toMatchObject({ taskId: paused.taskId, status: "idle" })
    expect(resumed?.lastReply).toContain("已写入")
    expect(readFileSync(join(root, "b.txt"), "utf8")).toBe("approved")

    expect(await adapter.approve(paused.taskId, true)).toBeNull()
    expect(await adapter.approve("missing", true)).toBeNull()
  })

  it("keeps a rejected task unexecuted", async () => {
    const { adapter } = setup(
      scriptedStream([
        { tools: [{ id: "c1", name: "write", args: { path: "c.txt", content: "x" } }] },
        { text: "已取消" },
      ]),
      { approvalPolicy: createDefaultApprovalPolicy({ BUTLER_V5_PI_APPROVAL: "always" }) },
    )

    const paused = await adapter.start({ projectId: "p1", goal: "写 c.txt" })
    const rejected = await adapter.approve(paused.taskId, false)
    expect(rejected?.status).toBe("idle")
    expect(() => readFileSync(join(root, "c.txt"), "utf8")).toThrow()
  })

  it("supports detached runs and exposes a settle hook", async () => {
    const { adapter } = setup(scriptedStream([{ text: "完成" }]), { detached: true })
    const ref = await adapter.start({ projectId: "p1", goal: "打个招呼" })
    expect(ref.status).toBe("running")

    await adapter.idle()
    const status = await adapter.status(ref.taskId)
    expect(status).toMatchObject({ taskId: ref.taskId, status: "idle" })
  })
})

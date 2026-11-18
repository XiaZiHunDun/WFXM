import { mkdtempSync, readFileSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { Effect } from "effect"
import type { LLMAdapter, LLMMessage, LLMTool, LLMToolCall } from "@butler/adapters"
import type { StreamFn } from "@butler/pi-agent"
import type { TaskMemoryEvent, TaskMemoryPort } from "@butler/ports/core/task-memory.js"
import { MemoryButlerSessionStore } from "@butler/runtime/butler/index.js"
import {
  createDefaultApprovalPolicy,
  GlobalAgentLock,
  MemoryPiTaskSessionStore,
  PiTaskRunner,
} from "@butler/runtime/execution/pi-task-runner.js"
import type { Model } from "@earendil-works/pi-ai"
import { createAssistantMessageEventStream, type AssistantMessage } from "@earendil-works/pi-ai"
import { createButlerAssembly, createButlerModelPort } from "./butler-assembly.js"

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

function fakeButlerAdapter(content = "好的", toolCalls: readonly LLMToolCall[] = []) {
  const calls: {
    messages: readonly LLMMessage[]
    tools?: readonly LLMTool[]
  }[] = []
  const adapter: LLMAdapter = {
    complete(messages, opts) {
      calls.push({ messages, ...(opts?.tools === undefined ? {} : { tools: opts.tools }) })
      return Effect.succeed({
        content,
        toolCalls,
        stopReason: toolCalls.length > 0 ? "tool_use" : "end_turn",
        usage: { inputTokens: 3, outputTokens: 2, totalTokens: 5 },
      })
    },
  }
  return { adapter, calls }
}

let root: string
let sequence = 0

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "butler-assembly-"))
  sequence = 0
})

afterEach(() => {
  rmSync(root, { recursive: true, force: true })
})

function makeRunner(
  streamFn: StreamFn,
  approval: "auto" | "always" = "auto",
  memory?: TaskMemoryPort,
): PiTaskRunner {
  return new PiTaskRunner({
    model: MODEL,
    apiKey: "fake",
    streamFn,
    approvalPolicy:
      approval === "always"
        ? createDefaultApprovalPolicy({ BUTLER_V5_PI_APPROVAL: "always" })
        : { check: () => ({ required: false }) },
    store: new MemoryPiTaskSessionStore(),
    lock: new GlobalAgentLock(),
    ...(memory === undefined ? {} : { memory }),
  })
}

describe("createButlerModelPort", () => {
  it("maps butler messages, tools and the assistant reply", async () => {
    const { adapter, calls } = fakeButlerAdapter("好的", [
      { id: "c1", name: "start_task", args: { goal: "修复登录" } },
    ])
    const port = createButlerModelPort(adapter)

    const reply = await port.complete({
      messages: [
        { role: "user", content: "帮我修登录" },
        {
          role: "assistant",
          content: "",
          toolCalls: [{ id: "c1", name: "start_task", args: { goal: "修复登录" } }],
        },
        { role: "tool", content: "已创建", toolCallId: "c1", toolName: "start_task" },
      ],
      tools: [
        {
          name: "start_task",
          description: "派发任务",
          parameters: {
            type: "object",
            properties: { goal: { type: "string" } },
            required: ["goal"],
          },
        },
      ],
    })

    expect(calls[0]?.messages[1]?.toolCalls?.[0]).toEqual({
      id: "c1",
      name: "start_task",
      args: { goal: "修复登录" },
    })
    expect(calls[0]?.messages[2]).toMatchObject({
      role: "tool",
      toolCallId: "c1",
      toolName: "start_task",
    })
    expect(calls[0]?.tools?.[0]?.parameters).toEqual({
      type: "object",
      properties: { goal: { type: "string" } },
      required: ["goal"],
    })
    expect(reply).toEqual({
      content: "好的",
      toolCalls: [{ id: "c1", name: "start_task", args: { goal: "修复登录" } }],
      usage: { inputTokens: 3, outputTokens: 2, totalTokens: 5 },
    })
  })
})

describe("createButlerAssembly", () => {
  it("serves rule routes without touching the model", async () => {
    const { adapter, calls } = fakeButlerAdapter()
    const assembly = await createButlerAssembly({
      projects: { p1: root },
      butlerAdapter: adapter,
      sessionStore: new MemoryButlerSessionStore(),
      taskRunner: makeRunner(scriptedStream([{ text: "unused" }])),
      env: {},
    })

    const result = await assembly.butler.handle({
      conversationId: "c1",
      userId: "u1",
      content: "/help",
    })

    expect(result.route).toBe("rule")
    expect(result.reply).toContain("/new")
    expect(calls).toHaveLength(0)
  })

  it("rejects tasks for projects missing from the root map", async () => {
    const { adapter } = fakeButlerAdapter()
    const assembly = await createButlerAssembly({
      projects: { p1: root },
      butlerAdapter: adapter,
      sessionStore: new MemoryButlerSessionStore(),
      taskRunner: makeRunner(scriptedStream([{ text: "unused" }])),
      env: {},
    })

    await expect(
      assembly.butler.handle({
        conversationId: "c1",
        userId: "u1",
        projectId: "nope",
        content: "/new 写文件",
      }),
    ).rejects.toThrow(/unknown project: nope/)
  })

  it("runs the pi task, pauses for approval and reports the outcome to memory", async () => {
    const { adapter, calls } = fakeButlerAdapter()
    const records: TaskMemoryEvent[] = []
    const taskMemory: TaskMemoryPort = {
      async recordTaskOutcome(event) {
        records.push(event)
      },
    }
    const assembly = await createButlerAssembly({
      projects: { p1: root },
      butlerAdapter: adapter,
      sessionStore: new MemoryButlerSessionStore(),
      taskRunner: makeRunner(
        scriptedStream([
          { tools: [{ id: "c1", name: "write", args: { path: "a.txt", content: "hi" } }] },
          { text: "已写入" },
        ]),
        "always",
        taskMemory,
      ),
      newTaskId: () => `t-${++sequence}`,
      env: {},
    })

    const created = await assembly.butler.handle({
      conversationId: "c1",
      userId: "u1",
      projectId: "p1",
      content: "/new 写 a.txt",
    })
    expect(created.taskId).toBe("t-1")
    expect(created.reply).toContain("需要确认")
    expect(created.reply).toContain("待执行：修改文件")

    const approved = await assembly.butler.handleApprovalCallback({
      conversationId: "c1",
      userId: "u1",
      taskId: "t-1",
      approved: true,
    })
    expect(approved.reply).toContain("已确认")
    expect(readFileSync(join(root, "a.txt"), "utf8")).toBe("hi")

    expect(records).toHaveLength(1)
    expect(records[0]).toMatchObject({
      taskId: "t-1",
      projectId: "p1",
      status: "completed",
      changedFiles: ["a.txt"],
    })
    expect(calls).toHaveLength(0)
  })

  it("requires a session store source", async () => {
    await expect(
      createButlerAssembly({
        projects: { p1: root },
        butlerAdapter: fakeButlerAdapter().adapter,
        taskRunner: makeRunner(scriptedStream([{ text: "unused" }])),
        env: {},
      }),
    ).rejects.toThrow(/requires either db or sessionStore/)
  })
})

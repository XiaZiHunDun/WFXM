/**
 * P4.0 spike — verify the two preconditions for a pi-native task layer:
 *   1. pi-ai can talk to our OpenAI-compatible provider with temperature=0.
 *   2. Agent state can be snapshotted and rehydrated into a new Agent.
 *
 * Run: set -a; . ~/.config/butler-v5/env; set +a; pnpm exec tsx scripts/p4-spike.ts
 */
import { Agent, type AgentTool, type StreamFn } from "../../../vendor/pi-agent/src/index.ts"
import {
  createAssistantMessageEventStream,
  retryAssistantCall,
  type AssistantMessage,
  type Model,
  type Usage,
} from "@earendil-works/pi-ai"
import { streamSimple } from "@earendil-works/pi-ai/api/openai-completions"

const baseUrl = process.env["MINIMAX_BASE_URL"] ?? ""
const apiKey = process.env["MINIMAX_CN_API_KEY"] ?? process.env["MINIMAX_API_KEY"] ?? ""
const modelId = process.env["MINIMAX_MODEL"] ?? "MiniMax-M2.1"

const usage: Usage = {
  input: 0,
  output: 0,
  cacheRead: 0,
  cacheWrite: 0,
  totalTokens: 0,
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
}

const model = {
  id: modelId,
  name: "minimax",
  api: "openai-completions",
  provider: "minimax",
  baseUrl,
  input: ["text"],
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
  contextWindow: 128_000,
  maxTokens: 256,
  reasoning: false,
} satisfies Model<"openai-completions">

async function checkModelLayer(): Promise<void> {
  console.log("[A] model layer")
  console.log("  baseUrl set:", Boolean(baseUrl), "| apiKey set:", Boolean(apiKey), "| model:", modelId)
  if (!baseUrl || !apiKey) {
    throw new Error("missing MINIMAX_BASE_URL / API key")
  }

  const stream = streamSimple(
    model,
    {
      messages: [{ role: "user", content: "只回复两个字：可用", timestamp: Date.now() }],
    } as never,
    { apiKey, temperature: 0, maxTokens: 32 },
  )

  let text = ""
  let done: AssistantMessage | undefined
  for await (const event of stream) {
    if (event.type === "text_delta") text += event.delta
    if (event.type === "done") done = event.message
    if (event.type === "error") throw new Error(`provider error: ${event.error.errorMessage}`)
  }
  console.log("  text:", JSON.stringify(text))
  console.log("  stopReason:", done?.stopReason, "| tokens:", done?.usage.totalTokens)
}

function fakeStream(reply: string): StreamFn {
  return () => {
    const stream = createAssistantMessageEventStream()
    const message: AssistantMessage = {
      role: "assistant",
      content: [{ type: "text", text: reply }],
      api: "openai-completions",
      provider: "faux",
      model: "faux",
      usage,
      stopReason: "stop",
      timestamp: Date.now(),
    }
    stream.push({ type: "start", partial: message })
    stream.push({ type: "text_start", contentIndex: 0, partial: message })
    stream.push({ type: "text_delta", contentIndex: 0, delta: reply, partial: message })
    stream.push({ type: "text_end", contentIndex: 0, content: reply, partial: message })
    stream.push({ type: "done", reason: "stop", message })
    return stream
  }
}

async function checkSessionRehydrate(): Promise<void> {
  console.log("[B] agent snapshot / rehydrate")

  const first = new Agent({
    initialState: { model, messages: [], tools: [] },
    streamFn: fakeStream("第一轮回复"),
  })
  await first.prompt("第一轮用户消息")
  const snapshot = first.state.messages
  console.log("  after turn 1:", snapshot.map((m) => m.role).join(" > "))

  const clone = JSON.parse(JSON.stringify(snapshot))
  const second = new Agent({
    initialState: { model, messages: clone, tools: [] },
    streamFn: fakeStream("第二轮回复"),
  })
  await second.prompt("第二轮用户消息")
  const roles = second.state.messages.map((m) => m.role)
  console.log("  after turn 2:", roles.join(" > "))
  console.log("  carried history:", roles.filter((r) => r === "user").length === 2)
}

function errorMessage(reason: string): AssistantMessage {
  return {
    role: "assistant",
    content: [],
    api: "openai-completions",
    provider: "faux",
    model: "faux",
    usage,
    stopReason: "error",
    errorMessage: reason,
    timestamp: Date.now(),
  }
}

async function checkRetry(): Promise<void> {
  console.log("[C] retry on 429")
  let attempts = 0
  const result = await retryAssistantCall(
    async () => {
      attempts += 1
      if (attempts < 3) return errorMessage("429 rate limit exceeded")
      return {
        role: "assistant",
        content: [{ type: "text", text: "ok" }],
        api: "openai-completions",
        provider: "faux",
        model: "faux",
        usage,
        stopReason: "stop",
        timestamp: Date.now(),
      }
    },
    { enabled: true, maxRetries: 3, baseDelayMs: 1 },
    undefined,
  )
  console.log("  attempts:", attempts, "| stopReason:", result.stopReason)
}

function toolCallStream(name: string, args: Record<string, unknown>): StreamFn {
  return () => {
    const stream = createAssistantMessageEventStream()
    const message: AssistantMessage = {
      role: "assistant",
      content: [{ type: "toolCall", id: "call-1", name, arguments: args }],
      api: "openai-completions",
      provider: "faux",
      model: "faux",
      usage,
      stopReason: "toolUse",
      timestamp: Date.now(),
    }
    stream.push({ type: "start", partial: message })
    stream.push({ type: "done", reason: "toolUse", message })
    return stream
  }
}

async function checkApprovalPause(): Promise<void> {
  console.log("[D] approval block + snapshot")
  let executed = false
  const tool: AgentTool = {
    name: "write",
    label: "write",
    description: "write a file",
    parameters: {
      type: "object",
      properties: { path: { type: "string" } },
      required: ["path"],
    },
    execute: async () => {
      executed = true
      return { content: [{ type: "text", text: "wrote" }] }
    },
  }

  const agent = new Agent({
    initialState: { model, messages: [], tools: [tool] },
    streamFn: toolCallStream("write", { path: "a.txt" }),
    beforeToolCall: () => ({ block: true, terminate: true, reason: "需要审批" }),
  })
  await agent.prompt("写文件")
  const roles = agent.state.messages.map((m) => m.role)
  console.log("  after blocked tool:", roles.join(" > "), "| executed:", executed)

  const resumed = new Agent({
    initialState: { model, messages: JSON.parse(JSON.stringify(agent.state.messages)), tools: [tool] },
    streamFn: fakeStream("已恢复"),
  })
  await resumed.prompt("继续")
  console.log("  after resume:", resumed.state.messages.map((m) => m.role).join(" > "))
}

async function main(): Promise<void> {
  await checkModelLayer()
  await checkSessionRehydrate()
  await checkRetry()
  await checkApprovalPause()
}

main().catch((error) => {
  console.error("SPIKE FAILED:", error instanceof Error ? error.message : error)
  process.exitCode = 1
})

/**
 * P4.1 smoke — exercise the pi-native task layer without a model.
 *
 * Run: pnpm exec tsx packages/runtime/scripts/p4.1-smoke.mts
 */
import assert from "node:assert/strict"
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
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
} from "../src/execution/pi-task-runner.js"

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

function messageOf(step: Step): AssistantMessage {
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

function streamOf(steps: readonly Step[]): StreamFn {
  let index = 0
  return () => {
    const step = steps[Math.min(index, steps.length - 1)] ?? { text: "done" }
    index += 1
    const message = messageOf(step)
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
const alwaysApprove = (): PiApprovalPolicy =>
  createDefaultApprovalPolicy({ BUTLER_V5_PI_APPROVAL: "always" })

function makeRunner(stream: StreamFn, extra: Record<string, unknown> = {}): PiTaskRunner {
  return new PiTaskRunner({
    model: MODEL,
    apiKey: "fake",
    streamFn: stream,
    approvalPolicy: autoApprove,
    ...extra,
  })
}

let root = ""
let taskSeq = 0
async function open(runner: PiTaskRunner): Promise<string> {
  taskSeq += 1
  const taskId = `task-${taskSeq}`
  await runner.open({ taskId, projectId: "smoke", cwd: root })
  return taskId
}

async function readTask(): Promise<void> {
  writeFileSync(join(root, "a.txt"), "hello smoke\n")
  const runner = makeRunner(
    streamOf([
      { tools: [{ id: "c1", name: "read", args: { path: "a.txt" } }] },
      { text: "read ok" },
    ]),
  )
  const taskId = await open(runner)
  const result = await runner.start(taskId, "read a.txt")
  assert.equal(result.status, "idle")
  assert.equal(result.toolCalls[0]?.normalizedName, "read_file")
  assert.match(result.toolCalls[0]?.output ?? "", /hello smoke/)
}

async function writeTask(): Promise<void> {
  const runner = makeRunner(
    streamOf([
      { tools: [{ id: "c1", name: "write", args: { path: "b.txt", content: "written" } }] },
      { text: "write ok" },
    ]),
  )
  const taskId = await open(runner)
  await runner.start(taskId, "write b.txt")
  assert.equal(readFileSync(join(root, "b.txt"), "utf8"), "written")
}

async function editTask(): Promise<void> {
  writeFileSync(join(root, "c.txt"), "port = 3000\n")
  const runner = makeRunner(
    streamOf([
      { tools: [{ id: "c1", name: "edit", args: { path: "c.txt", oldText: "3000", newText: "8080" } }] },
      { text: "edit ok" },
    ]),
  )
  const taskId = await open(runner)
  await runner.start(taskId, "edit c.txt")
  assert.match(readFileSync(join(root, "c.txt"), "utf8"), /8080/)
}

async function bashTask(): Promise<void> {
  const runner = makeRunner(
    streamOf([
      { tools: [{ id: "c1", name: "bash", args: { command: "echo smoke-ok" } }] },
      { text: "bash ok" },
    ]),
  )
  const taskId = await open(runner)
  const result = await runner.start(taskId, "run echo")
  assert.equal(result.toolCalls[0]?.normalizedName, "run_command")
  assert.match(result.toolCalls[0]?.output ?? "", /smoke-ok/)
}

async function approvalApprove(): Promise<void> {
  const runner = makeRunner(
    streamOf([
      { tools: [{ id: "c1", name: "write", args: { path: "d.txt", content: "approved" } }] },
      { text: "approved ok" },
    ]),
    { approvalPolicy: alwaysApprove() },
  )
  const taskId = await open(runner)
  const paused = await runner.start(taskId, "write d.txt")
  assert.equal(paused.status, "paused")
  assert.equal(paused.pendingStep?.toolName, "write")
  await runner.resume(taskId, { approved: true })
  assert.equal(readFileSync(join(root, "d.txt"), "utf8"), "approved")
}

async function approvalDeny(): Promise<void> {
  const runner = makeRunner(
    streamOf([
      { tools: [{ id: "c1", name: "write", args: { path: "e.txt", content: "denied" } }] },
      { text: "denied ok" },
    ]),
    { approvalPolicy: alwaysApprove() },
  )
  const taskId = await open(runner)
  await runner.start(taskId, "write e.txt")
  await runner.resume(taskId, { approved: false, note: "不要写" })
  assert.throws(() => readFileSync(join(root, "e.txt"), "utf8"))
}

async function singleFlight(): Promise<void> {
  let release!: () => void
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  let calls = 0
  const stream: StreamFn = () => {
    calls += 1
    if (calls === 1) {
      return gate.then(() => streamOf([{ text: "first" }])())
    }
    return streamOf([{ text: "second" }])()
  }
  const lock = new GlobalAgentLock()
  const runner = makeRunner(stream, { lock })
  const firstId = await open(runner)
  const secondId = await open(runner)
  const first = runner.start(firstId, "first")
  await new Promise((resolve) => setTimeout(resolve, 20))
  const second = runner.start(secondId, "second")
  await new Promise((resolve) => setTimeout(resolve, 20))
  assert.equal(lock.activeTaskId, firstId)
  assert.equal(lock.queueLength, 1)
  release()
  await Promise.all([first, second])
  assert.equal(lock.activeTaskId, null)
}

async function snapshotRestore(): Promise<void> {
  const store = new MemoryPiTaskSessionStore()
  const first = makeRunner(
    streamOf([
      { tools: [{ id: "c1", name: "read", args: { path: "a.txt" } }] },
      { text: "turn one" },
    ]),
    { store },
  )
  writeFileSync(join(root, "a.txt"), "history\n")
  const taskId = await open(first)
  await first.start(taskId, "turn one")

  const second = makeRunner(streamOf([{ text: "turn two" }]), { store })
  await second.load(taskId)
  const result = await second.start(taskId, "turn two")
  assert.match(result.reply, /turn two/)
  const record = await store.load(taskId)
  const users = (record?.snapshot.messages as { role: string }[]).filter((m) => m.role === "user")
  assert.equal(users.length, 2)
}

const cases: [string, () => Promise<void>][] = [
  ["read", readTask],
  ["write", writeTask],
  ["edit", editTask],
  ["bash", bashTask],
  ["approval-approve", approvalApprove],
  ["approval-deny", approvalDeny],
  ["single-flight", singleFlight],
  ["snapshot-restore", snapshotRestore],
]

async function main(): Promise<void> {
  root = mkdtempSync(join(tmpdir(), "pi-smoke-"))
  let failed = 0
  try {
    for (const [name, run] of cases) {
      try {
        await run()
        console.log(`PASS ${name}`)
      } catch (error) {
        failed += 1
        console.error(`FAIL ${name}: ${error instanceof Error ? error.message : String(error)}`)
      }
    }
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
  if (failed > 0) process.exitCode = 1
}

main().catch((error: unknown) => {
  console.error("SMOKE FAILED:", error instanceof Error ? error.message : String(error))
  process.exitCode = 1
})

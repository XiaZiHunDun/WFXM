/**
 * P4.1 eval driver: run a capability task through the pi-native task layer.
 *
 * Unlike `run-task.ts`, this path does not use the WeChat acceptance harness.
 * It seeds a scratch workspace, drives `PiTaskRunner` with the real model, and
 * emits the same TraceEvent/result envelope so the existing agent-eval adapter
 * can consume it unchanged.
 */
import { cpSync, mkdtempSync, readFileSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import {
  createPiStreamFn,
  resolvePiModelFromEnv,
} from "../../packages/runtime/src/execution/pi-model.js"
import {
  bashNeedsApproval,
  MemoryPiTaskSessionStore,
  PiTaskRunner,
  type PiApprovalPolicy,
  type PiTaskTurnResult,
} from "../../packages/runtime/src/execution/pi-task-runner.js"
import { normalizePiToolName } from "../../packages/runtime/src/execution/pi-tool-name-map.js"
import { buildRepoMap } from "../../packages/runtime/src/execution/repo-map.js"
import { DEFAULT_PI_TASK_SYSTEM_PROMPT } from "../../packages/runtime/src/execution/pi-task-prompt.js"
import {
  diffWorkspace,
  emitResult,
  resolveInsideWorkspace,
  runTests,
  seedWorkspace,
} from "./eval-utils.js"
import type { EvalTaskInput, TraceEvent } from "./task-input.js"

const APPROVAL_TOOLS = new Set(["write", "edit"])
const CONFIRM_PATTERN = /确认|同意|批准|好|可以|yes|ok/i

interface ToolCallRecord {
  readonly name: string
  readonly args?: Record<string, unknown>
}

export async function runPiEvalTask(task: EvalTaskInput): Promise<void> {
  if (task.realModel !== true) {
    throw new Error("pi 驱动需要 --real（真实模型）运行")
  }
  const hint = task.runtimeHints?.wfxm
  if (hint?.rag) {
    throw new Error("pi 驱动暂不支持 RAG 任务")
  }

  const traceId = crypto.randomUUID()
  const runId = task.id
  const trace: TraceEvent[] = []
  let seq = 0
  let rootSpanId: string | null = null
  const push = (
    type: string,
    payload: Record<string, unknown>,
    actor: TraceEvent["actor"] = { kind: "system", id: "wfxm" },
    tsOverride?: number,
  ): void => {
    const spanId = crypto.randomUUID()
    trace.push({
      schema: "wfxm.trace/0",
      traceId,
      runId,
      runtime: "wfxm",
      seq: seq++,
      ts: new Date(tsOverride ?? Date.now()).toISOString(),
      type,
      spanId,
      parentSpanId: rootSpanId,
      actor,
      payload,
    })
    if (type === "run.start") rootSpanId = spanId
  }

  const workspaceRoot = mkdtempSync(join(tmpdir(), "wfxm-pi-"))
  const startedAt = Date.now()
  push("run.start", {
    taskId: task.id,
    scenarioId: hint?.scenarioId ?? null,
    channel: "pi-task-runner",
    model: "real",
    engine: "pi-task-runner",
  })

  const config = resolvePiModelFromEnv()
  const store = new MemoryPiTaskSessionStore()
  const policy: PiApprovalPolicy = {
    check: ({ toolName, args }) => {
      if (APPROVAL_TOOLS.has(toolName)) {
        return { required: true, reason: "修改文件前需要你确认。" }
      }
      if (toolName === "bash") {
        const command =
          args && typeof args === "object" && "command" in args
            ? String((args as { command?: unknown }).command ?? "")
            : ""
        if (bashNeedsApproval(command)) {
          return { required: true, reason: "命令可能修改或删除文件，需要你确认。" }
        }
      }
      return { required: false }
    },
  }
  const runner = new PiTaskRunner({
    model: config.model,
    apiKey: config.apiKey,
    streamFn: createPiStreamFn({ model: config.model, apiKey: config.apiKey }),
    approvalPolicy: policy,
    store,
    maxToolCalls: task.budget?.maxToolCalls ?? 24,
  })

  const replies: string[] = []
  const statuses: number[] = []
  const toolNames: string[] = []
  const toolResults: { name: string; ok: boolean }[] = []
  const toolCalls: ToolCallRecord[] = []
  const modelTotals = { calls: 0, inputTokens: 0, outputTokens: 0, totalTokens: 0 }
  let firstDecision: string | undefined
  let totalToolCalls = 0
  let paused = false

  const recordTurn = (result: PiTaskTurnResult): void => {
    for (const call of result.toolCalls) {
      toolNames.push(call.normalizedName)
      toolResults.push({ name: call.normalizedName, ok: call.ok })
      toolCalls.push({ name: call.normalizedName, args: { ...call.args } })
      push(
        "tool.call",
        {
          name: call.normalizedName,
          source: "pi-task-runner",
          rawName: call.rawName,
          args: call.args,
        },
        { kind: "agent", id: "wfxm" },
      )
      push("tool.result", {
        name: call.normalizedName,
        ok: call.ok,
        durationMs: call.durationMs,
        ...(call.reason ? { reason: call.reason } : {}),
      })
    }
    if (result.pendingStep) {
      const normalized = normalizePiToolName(result.pendingStep.toolName)
      toolNames.push(normalized)
      push("approval.request", {
        capability: normalized,
        rawName: result.pendingStep.toolName,
        args: result.pendingStep.args,
        question: result.pendingStep.reason,
      })
    }
    modelTotals.calls += 1
    modelTotals.inputTokens += result.usage.inputTokens
    modelTotals.outputTokens += result.usage.outputTokens
    modelTotals.totalTokens += result.usage.totalTokens
  }

  try {
    if (task.repoFixture) {
      cpSync(task.repoFixture, workspaceRoot, { recursive: true })
      push("test.run", { phase: "setup", repoFixture: task.repoFixture })
    }
    seedWorkspace(workspaceRoot, hint?.fixtures?.seedFiles ?? [])
    // Inject the same repository map the butler task adapter uses, so the eval
    // driver measures the production path instead of a blind-exploration path.
    const repoMap = await buildRepoMap(workspaceRoot)
    await runner.open({
      taskId: task.id,
      projectId: "eval",
      cwd: workspaceRoot,
      summary: `Evaluation task ${task.id}`,
      ...(repoMap.length === 0
        ? {}
        : { systemPrompt: `${DEFAULT_PI_TASK_SYSTEM_PROMPT}\n\n${repoMap}` }),
    })

    const testsBefore = task.tests ? await runTests(workspaceRoot, task.tests) : undefined
    if (testsBefore) {
      push("test.run", {
        phase: "before",
        command: testsBefore.command,
        exitCode: testsBefore.exitCode,
        passed: testsBefore.passed,
      })
    }

    const timeoutMs = task.timeoutMs ?? 180_000
    for (const [index, content] of task.turns.entries()) {
      push("turn.start", { index: index + 1, input: content }, { kind: "owner", id: "u-owner" })
      const turnStartedAt = Date.now()
      const approved = paused && CONFIRM_PATTERN.test(content)
      const result = paused
        ? await runner.resume(task.id, { approved })
        : await runner.start(task.id, content, { timeoutMs })
      paused = result.status === "paused"
      recordTurn(result)

      const reply = result.pendingStep ? result.pendingStep.reason : result.reply
      replies.push(reply)
      statuses.push(result.status === "failed" ? 500 : 200)
      totalToolCalls += result.toolCalls.length
      if (index === 0) firstDecision = paused ? "WaitForApproval" : "Respond"

      push("turn.end", {
        status: result.status,
        finalDecision: paused ? "WaitForApproval" : "Respond",
        toolCalls: result.toolCalls.length,
        replyLen: reply.length,
        latencyMs: Date.now() - turnStartedAt,
      })
    }

    const durationMs = Date.now() - startedAt
    const repoDiff = task.repoFixture ? diffWorkspace(task.repoFixture, workspaceRoot) : null
    if (repoDiff) push("workspace.diff", { ...repoDiff })
    const testsAfter = task.tests ? await runTests(workspaceRoot, task.tests) : undefined
    if (testsAfter) {
      push("test.run", {
        phase: "after",
        command: testsAfter.command,
        exitCode: testsAfter.exitCode,
        passed: testsAfter.passed,
      })
    }
    const workspace: Record<string, string | null> = {}
    for (const path of task.workspacePaths ?? []) {
      try {
        workspace[path] = readFileSync(resolveInsideWorkspace(workspaceRoot, path), "utf8")
      } catch {
        workspace[path] = null
      }
    }
    push("run.end", { status: "ok", durationMs })

    emitResult({
      status: statuses[0] ?? 0,
      statuses,
      reply: replies[0] ?? "",
      replies,
      finalDecision: firstDecision,
      steps: totalToolCalls,
      turns: statuses.length,
      toolNames,
      toolResults,
      toolCalls,
      engine: "pi-task-runner",
      ...(modelTotals.calls > 0 ? { model: modelTotals } : {}),
      ...(task.tests && testsBefore && testsAfter
        ? {
            tests: {
              command: task.tests.command,
              before: testsBefore,
              after: testsAfter,
            },
          }
        : {}),
      ...(Object.keys(workspace).length > 0 ? { workspace } : {}),
      ...(repoDiff ? { diff: repoDiff } : {}),
      durationMs,
      trace,
    })
  } finally {
    await runner.close(task.id).catch(() => undefined)
    rmSync(workspaceRoot, { recursive: true, force: true })
  }
}

async function main(): Promise<void> {
  const task = JSON.parse(readFileSync(0, "utf8")) as EvalTaskInput
  await runPiEvalTask(task)
}

if (process.argv[1]?.endsWith("run-pi-task.mts")) {
  main().catch((error: unknown) => {
    emitResult({ error: error instanceof Error ? error.message : String(error) })
    process.exit(1)
  })
}

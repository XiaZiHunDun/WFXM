/**
 * P4.2 butler eval driver.
 *
 * Deterministic fixture run of `ButlerRuntime`: routing, rule fast-paths,
 * approval chaining and profile recall — no network, no workspace writes.
 * The agent-eval adapter consumes the `__EVAL_RESULT__` envelope.
 */
import { readFileSync } from "node:fs"
import type { ButlerMemoryPort } from "../../packages/ports/src/core/butler-memory.js"
import type { ButlerTaskPort, ButlerTaskRef } from "../../packages/ports/src/core/butler-task.js"
import type { ButlerModelPort } from "../../packages/runtime/src/butler/model-port.js"
import { ButlerRuntime } from "../../packages/runtime/src/butler/butler-runtime.js"
import { MemoryButlerSessionStore } from "../../packages/runtime/src/butler/session-store.js"
import { emitResult } from "./eval-utils.js"

interface FixtureReply {
  readonly content?: string
  readonly toolCalls?: readonly {
    readonly id: string
    readonly name: string
    readonly args: Record<string, unknown>
  }[]
}

interface ButlerFixtures {
  readonly model: readonly FixtureReply[]
  readonly tasks?: readonly ButlerTaskRef[]
  readonly userMemory?: readonly {
    readonly title: string
    readonly text: string
    /** Entries with keywords only match queries containing one of them. */
    readonly keywords?: readonly string[]
  }[]
  readonly projectId?: string
  readonly activeTaskId?: string
  /** Card payload per turn; `null` means a normal text turn. */
  readonly approvalPayloads?: readonly (string | null)[]
}

interface ButlerEvalInput {
  readonly id: string
  readonly turns: readonly string[]
  readonly runtimeHints: {
    readonly wfxm: {
      readonly scenarioId: string
      readonly fixtures: ButlerFixtures
    }
  }
}

async function runButlerEvalTask(task: ButlerEvalInput): Promise<void> {
  const fixtures = task.runtimeHints.wfxm.fixtures
  const projectId = fixtures.projectId ?? "proj-eval"
  const userMemory = fixtures.userMemory ?? []
  const projectTasks = [...(fixtures.tasks ?? [])]
  const approvals: { taskId: string; approved: boolean }[] = []
  const started: string[] = []
  let modelCalls = 0
  let memoryRecalled = false
  let memoryRecallTurns = 0
  const replies: string[] = []

  const model: ButlerModelPort = {
    async complete({ messages }) {
      const joined = messages.map((message) => message.content).join("\n")
      if (userMemory.some((entry) => joined.includes(entry.title))) {
        memoryRecalled = true
        memoryRecallTurns += 1
      }
      const step = fixtures.model[Math.min(modelCalls, fixtures.model.length - 1)] ?? {
        content: "好的",
      }
      modelCalls += 1
      return {
        content: step.content ?? "",
        ...(step.toolCalls === undefined ? {} : { toolCalls: step.toolCalls }),
      }
    },
  }

  const tasks: ButlerTaskPort = {
    async start(input) {
      const task: ButlerTaskRef = {
        taskId: `task-${started.length + 1}`,
        projectId: input.projectId,
        status: "idle",
      }
      started.push(task.taskId)
      projectTasks.push(task)
      return task
    },
    async status(taskId) {
      return projectTasks.find((task) => task.taskId === taskId) ?? null
    },
    async list(pid) {
      return pid === undefined
        ? projectTasks
        : projectTasks.filter((task) => task.projectId === pid)
    },
    async approve(taskId, approved) {
      approvals.push({ taskId, approved })
      const task = projectTasks.find((entry) => entry.taskId === taskId)
      return task ? { ...task, status: "idle", pending: undefined } : null
    },
  }

  const memory: ButlerMemoryPort = {
    async recordSessionSummary() {
      // Nothing to persist in an eval run.
    },
    async recallUserMemory(query) {
      if (query.trim().length === 0) return userMemory
      return userMemory.filter(
        (entry) =>
          entry.keywords === undefined || entry.keywords.some((keyword) => query.includes(keyword)),
      )
    },
  }

  const butler = new ButlerRuntime({
    model,
    tasks,
    memory,
    store: new MemoryButlerSessionStore(),
    clock: () => "2026-11-17T10:00:00.000Z",
  })

  let last: Awaited<ReturnType<ButlerRuntime["handle"]>> | undefined
  for (const [index, turn] of task.turns.entries()) {
    const payload = fixtures.approvalPayloads?.[index] ?? null
    if (payload !== null) {
      last = await butler.handleApprovalCallback({
        conversationId: `c-${task.id}`,
        userId: "owner",
        taskId: payload.slice(payload.indexOf(":") + 1),
        approved: payload.startsWith("approve:"),
      })
    } else {
      last = await butler.handle({
        conversationId: `c-${task.id}`,
        userId: "owner",
        projectId,
        content: turn,
        ...(fixtures.activeTaskId === undefined ? {} : { activeTaskId: fixtures.activeTaskId }),
      })
    }
    replies.push(last.reply)
  }

  const traceId = crypto.randomUUID()
  const trace = [
    {
      schema: "wfxm.trace/0",
      traceId,
      runId: task.id,
      runtime: "wfxm-butler",
      seq: 0,
      ts: "2026-11-17T10:00:00.000Z",
      type: "run.start",
      actor: { kind: "system", id: "butler-eval" },
      payload: { turns: task.turns.length },
    },
    {
      schema: "wfxm.trace/0",
      traceId,
      runId: task.id,
      runtime: "wfxm-butler",
      seq: 1,
      ts: "2026-11-17T10:00:00.000Z",
      type: "run.end",
      actor: { kind: "system", id: "butler-eval" },
      payload: { status: "ok" },
    },
  ]

  emitResult({
    id: task.id,
    turns: task.turns.length,
    replies,
    reply: replies.at(-1),
    butler: {
      route: last?.route,
      ...(last?.rule === undefined ? {} : { rule: last.rule }),
      ...(last?.taskId === undefined ? {} : { taskId: last.taskId }),
      approvals,
      started,
      modelCalls,
      memoryRecalled,
      memoryRecallTurns,
      rewrites: last?.traces.filter((trace) => trace === "memory:rewrite").length ?? 0,
    },
    ...(modelCalls > 0 ? { model: { calls: modelCalls } } : {}),
    trace,
  })
}

async function main(): Promise<void> {
  const task = JSON.parse(readFileSync(0, "utf8")) as ButlerEvalInput
  await runButlerEvalTask(task)
}

main().catch((error: unknown) => {
  emitResult({ error: error instanceof Error ? error.message : String(error) })
  process.exitCode = 1
})

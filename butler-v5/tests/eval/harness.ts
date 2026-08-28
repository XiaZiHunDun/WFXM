/**
 * Eval scenario harness — wraps `runButlerLoop` with metric capture.
 *
 * Each scenario is a vitest test that calls `runEvalScenario({...})`,
 * asserts expectations, and reads `result.metrics` + `result.painPoints`.
 * The harness produces deterministic metrics for the same scripted adapter.
 */
import { EventBridge } from "@butler/persistence/event-bridge.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { createRuntimeStore } from "@butler/persistence"
import { makeTestDb } from "@butler/persistence/testing.js"
import { makeWiring, type Wiring } from "@butler/api/wiring.js"
import { runButlerLoop, type ButlerLoopLogger } from "@butler/api/wechat-inbound-butler.js"
import type { LLMAdapter } from "@butler/adapters"
import type { ModelDecisionTag } from "@butler/domain/runtime.js"
import { detectPainPoints, type EvalMetrics, type EvalResult } from "./metrics.js"

/** Adapter that exposes call counters — extends LLMAdapter with introspection. */
export interface InstrumentedAdapter {
  readonly adapter: LLMAdapter
  readonly callCount: () => number
  readonly getCalls: () => readonly { messagesCount: number; toolsCount: number }[]
  readonly latencyByCall?: () => readonly number[]
}

export interface RunScenarioInput {
  readonly name: string
  readonly content: string
  readonly fromUserId?: string
  readonly projectId?: string
  readonly conversationId?: string
  readonly env?: Readonly<Record<string, string>>
  readonly adapter: InstrumentedAdapter
  readonly allowedToolNames?: readonly string[]
}

const silentLogger: ButlerLoopLogger = {
  warn: (msg, extra) => {
    // eslint-disable-next-line no-console -- optional debug output behind EVAL_DEBUG=1
    if (process.env["EVAL_DEBUG"]) console.error(`[loop warn] ${msg}`, extra ?? "")
  },
  error: (msg, err) => {
    // eslint-disable-next-line no-console -- optional debug output behind EVAL_DEBUG=1
    if (process.env["EVAL_DEBUG"]) console.error(`[loop error] ${msg}`, err)
  },
}

/** Extract capability names from conversation-loop traces (`<name>@<iter>: ...`). */
function capabilitiesFromTraces(traces: readonly string[]): readonly string[] {
  const out: string[] = []
  for (const t of traces) {
    const m = /^([a-z][a-z_0-9]*)@\d+:/.exec(t)
    if (m && m[1]) out.push(m[1])
  }
  return out
}

export async function runEvalScenario(input: RunScenarioInput): Promise<EvalResult> {
  const totalStart = Date.now()
  const db = await makeTestDb()
  const bridge = new EventBridge({ db: db.db, workerId: "w-eval" })
  const runtimeStore = createRuntimeStore(db.db)
  const runEngine = new RunEngine(runtimeStore)
  const wiring: Wiring = makeWiring({
    bridge,
    workerId: "w-eval",
    runtimeStore,
    runEngine,
    db: db.db,
    backfillConversation: async () => undefined,
  })
  const setupMs = Date.now() - totalStart

  const loopStart = Date.now()
  const errors: string[] = []
  let result_metrics: EvalMetrics
  let successFlag = false

  try {
    const result = await runButlerLoop({
      wiring,
      conversationId:
        input.conversationId ?? `c-eval-${Math.random().toString(36).slice(2, 10)}`,
      content: input.content,
      fromUserId: input.fromUserId ?? "owner-eval",
      projectId: input.projectId ?? "p-eval",
      env: input.env ?? {},
      logger: silentLogger,
      adapter: input.adapter.adapter,
      ...(input.allowedToolNames ? { allowedToolNames: input.allowedToolNames } : {}),
    })
    const capabilityCalls = capabilitiesFromTraces(result.traces)
    const capabilitiesByName: Record<string, number> = {}
    for (const c of capabilityCalls) {
      capabilitiesByName[c] = (capabilitiesByName[c] ?? 0) + 1
    }
    result_metrics = {
      scenario: input.name,
      setupMs,
      loopMs: Date.now() - loopStart,
      totalMs: Date.now() - totalStart,
      iterations: result.iterations,
      llmCalls: input.adapter.callCount(),
      capabilityCalls,
      capabilitiesByName,
      finalDecision: result.finalDecision as ModelDecisionTag | null,
      reply: result.reply,
      replyLength: result.reply.length,
      errors,
      traces: result.traces,
      success: false,
    }
    successFlag = true
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    if (process.env["EVAL_DEBUG"]) {
      // eslint-disable-next-line no-console -- optional debug output behind EVAL_DEBUG=1
      console.error(`[eval:${input.name}] throw:`, msg)
      if (err instanceof Error && err.stack) {
        // eslint-disable-next-line no-console -- optional debug output behind EVAL_DEBUG=1
        console.error(err.stack)
      }
    }
    errors.push(msg)
    result_metrics = {
      scenario: input.name,
      setupMs,
      loopMs: Date.now() - loopStart,
      totalMs: Date.now() - totalStart,
      iterations: 0,
      llmCalls: input.adapter.callCount(),
      capabilityCalls: [],
      capabilitiesByName: {},
      finalDecision: null,
      reply: "",
      replyLength: 0,
      errors,
      traces: [],
      success: false,
    }
  }

  await db.close()

  const finalMetrics: EvalMetrics = { ...result_metrics, success: successFlag }
  const painPoints = detectPainPoints(finalMetrics)
  return { metrics: finalMetrics, painPoints }
}

/** Format a one-line metric summary for console output during pnpm test runs. */
export function formatMetricLine(metrics: EvalMetrics): string {
  const cap = Object.entries(metrics.capabilitiesByName)
    .map(([n, c]) => `${n}×${c}`)
    .join(",")
  const errSuffix = metrics.errors.length > 0 ? ` ERR=${metrics.errors.length}` : ""
  return [
    `[eval:${metrics.scenario}]`,
    `setup=${metrics.setupMs}ms`,
    `loop=${metrics.loopMs}ms`,
    `iter=${metrics.iterations}`,
    `llm=${metrics.llmCalls}`,
    `cap=${cap || "none"}`,
    `decision=${metrics.finalDecision ?? "(none)"}`,
    `success=${metrics.success}${errSuffix}`,
  ].join(" ")
}

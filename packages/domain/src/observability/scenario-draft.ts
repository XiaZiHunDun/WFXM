/**
 * Phase 6 P1: project one turn's trace events into an acceptance-scenario
 * draft. Pure (no I/O) so both the CLI (`pnpm trace:to-scenario`) and the
 * WeChat `/转用例` command share exactly one shape.
 */
import type { TraceEvent } from "./local-trace.js"

export interface ScenarioDraft {
  readonly version: 1
  readonly generatedAt: string
  readonly turnId: string
  readonly conversationId: string | null
  readonly runId: string | null
  readonly observed: {
    readonly runStatus: string | null
    readonly errorCode: string | null
    readonly toolCalls: readonly string[]
    readonly finalDecision: string | null
  }
  readonly events: readonly TraceEvent[]
  readonly note: string
}

export function slugify(input: string): string {
  const slug = input
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
  return slug.length > 0 ? slug.slice(0, 60) : "turn"
}

function detailString(event: TraceEvent, key: string): string | null {
  const value = (event.detail ?? {})[key]
  return typeof value === "string" ? value : null
}

/** Terminal events, in both emitted shapes (see `isFailedRunTrace`). */
function findTerminal(events: readonly TraceEvent[]): TraceEvent | undefined {
  return events.find(
    (event) =>
      (event.kind === "run" && (event.name === "finish" || event.name === "failure")) ||
      (event.kind === "step" && (event.name === "run_failed" || event.name === "run_succeeded")),
  )
}

function isFailureTerminal(event: TraceEvent): boolean {
  if (event.kind === "step") return event.name === "run_failed"
  return event.status === "error"
}

export function buildScenarioDraft(
  events: readonly TraceEvent[],
  options: { readonly turnId: string; readonly generatedAt?: string },
): ScenarioDraft {
  const first = events[0]
  const terminal = findTerminal(events)
  const toolCalls = events
    .filter((event) => event.kind === "step" && event.name.startsWith("tool_"))
    .map((event) => {
      const detail = event.detail ?? {}
      const named = detail["tool"] ?? detail["name"]
      return typeof named === "string" ? named : event.name
    })

  return {
    version: 1,
    generatedAt: options.generatedAt ?? new Date().toISOString(),
    turnId: options.turnId,
    conversationId: first?.conversationId ?? null,
    runId: first?.runId ?? null,
    observed: {
      runStatus:
        terminal === undefined ? null : isFailureTerminal(terminal) ? "failed" : "succeeded",
      errorCode: terminal === undefined ? null : detailString(terminal, "code"),
      toolCalls,
      finalDecision: terminal === undefined ? null : detailString(terminal, "decision"),
    },
    events,
    note: "由 `pnpm trace:to-scenario` 生成的草稿。请人工补齐输入与期望，再移入正式场景目录；脚本不会自动改断言。",
  }
}

export function renderDraftTest(draft: ScenarioDraft): string {
  return `/**
 * 草稿（自动生成，默认 skip）— 请勿直接放进 CI。
 *
 * turnId: ${draft.turnId}
 * 生成时间: ${draft.generatedAt}
 * 观察到的结果: ${JSON.stringify(draft.observed)}
 *
 * 待办：
 *   1. 从 ${draft.turnId}.json 里提取用户输入与关键工具调用；
 *   2. 写清"应该发生什么"（不仅是"实际发生了什么"）；
 *   3. 移入 tests/acceptance/scenarios/ 并去掉 .skip。
 */
import { describe, it } from "vitest"

describe.skip("[draft] ${draft.turnId}", () => {
  it("TODO: 描述这次线上失败应被回归保护的行为", () => {
    // TODO: 用 makeAcceptanceApp() 重现，并断言最终状态与错误码。
  })
})
`
}

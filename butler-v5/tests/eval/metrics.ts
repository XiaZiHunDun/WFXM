/**
 * Eval scenario metrics + pain-point heuristics.
 *
 * Distinct from `@butler/domain/observability/local-trace`: metrics here
 * describe one entire scenario run (per-scenario totals) and stay in the
 * test process. The OTEL pipeline is not invoked; this is owner-realistic
 * exploration, not telemetry.
 */
import type { ModelDecisionTag } from "@butler/domain/runtime.js"

export type PainSeverity = "info" | "warning" | "issue"

export interface PainPoint {
  readonly severity: PainSeverity
  readonly category: string
  readonly message: string
}

export interface EvalMetrics {
  readonly scenario: string
  readonly setupMs: number
  readonly loopMs: number
  readonly totalMs: number
  readonly iterations: number
  readonly llmCalls: number
  readonly capabilityCalls: readonly string[]
  readonly capabilitiesByName: Readonly<Record<string, number>>
  readonly finalDecision: ModelDecisionTag | null
  readonly reply: string
  readonly replyLength: number
  readonly errors: readonly string[]
  readonly traces: readonly string[]
  readonly success: boolean
}

export interface EvalResult {
  readonly metrics: EvalMetrics
  readonly painPoints: readonly PainPoint[]
}

const LOOP_CAP = 5

/** Heuristic detection — flag loop exhaustion, repeated tool calls, decode failures, slow paths. */
export function detectPainPoints(metrics: EvalMetrics): readonly PainPoint[] {
  const out: PainPoint[] = []
  if (metrics.iterations >= LOOP_CAP) {
    out.push({
      severity: "warning",
      category: "loop-exhausted",
      message: `loop hit cap (${metrics.iterations} iterations)`,
    })
  }
  for (const [name, count] of Object.entries(metrics.capabilitiesByName)) {
    if (count >= 3) {
      out.push({
        severity: "warning",
        category: "tool-retry",
        message: `capability ${name} called ${count} times`,
      })
    }
  }
  if (metrics.traces.some((t) => /decode failed/i.test(t))) {
    out.push({
      severity: "warning",
      category: "decision-decode-fail",
      message: `Decision decoder failed at least once during loop`,
    })
  }
  if (metrics.loopMs > 2000 && metrics.iterations <= 2) {
    out.push({
      severity: "info",
      category: "slow-loop",
      message: `loop took ${metrics.loopMs}ms with only ${metrics.iterations} iterations`,
    })
  }
  if (metrics.errors.length > 0) {
    out.push({
      severity: "issue",
      category: "errors",
      message: `${metrics.errors.length} error(s): ${metrics.errors.slice(0, 3).join("; ")}`,
    })
  }
  if (!metrics.success) {
    out.push({
      severity: "issue",
      category: "scenario-fail",
      message: `scenario expectation failed`,
    })
  }
  return out
}

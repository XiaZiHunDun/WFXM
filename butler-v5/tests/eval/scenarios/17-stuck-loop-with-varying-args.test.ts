/**
 * Scenario 17: stuck-loop-with-varying-args — focuses on the case where
 * the LLM calls the same capability but with DIFFERENT args each time.
 * The stuck-loop signature is (name, args), so this should NOT trip the
 * detector; the loop runs normally to Respond.
 *
 * Validates: stuck-loop detection is args-aware (not false-positive on
 * legitimate varied invocations of the same capability).
 */
import { describe, expect, it } from "vitest"
import { runEvalScenario, formatMetricLine } from "../harness.js"
import { decisionResponse, makeScriptedAdapter, toolCallResponse } from "../mock-llm-scripted.js"

describe("eval/17 stuck-loop-with-varying-args", () => {
  // D82 T1: this was the only multi-turn eval scenario still on the
  // global 10s testTimeout. Alone it needs ~4s, but three tool calls
  // make it pay one fatigue cooldown (DEFAULT_COOLDOWN_MS), and
  // concurrent PGlite migrations in the full-suite run push it to
  // ~8.3s — right at the edge. Every other multi-turn scenario already
  // overrides this (15 = 60s; 09/13/14/19/20/21/22 = 30s).
  it(
    "LLM invokes recall_history with varied limits → no stuck-loop, normal Respond",
    { timeout: 30_000 },
    async () => {
      const adapter = makeScriptedAdapter({
        responses: [
          toolCallResponse([{ id: "tc-1", name: "recall_history", args: { limit: 5 } }]),
          toolCallResponse([{ id: "tc-2", name: "recall_history", args: { limit: 10 } }]),
          toolCallResponse([{ id: "tc-3", name: "recall_history", args: { limit: 20 } }]),
          decisionResponse({
            _tag: "Respond",
            content: "已 recall 多条",
          }),
        ],
      })
      const result = await runEvalScenario({
        name: "17-stuck-loop-varying-args",
        content: "帮我看历史",
        fromUserId: "owner-1",
        projectId: "p-1",
        adapter,
      })

      // eslint-disable-next-line no-console -- eval scenarios log metrics to stdout
      console.log(formatMetricLine(result.metrics))

      expect(result.metrics.success).toBe(true)
      expect(result.metrics.iterations).toBeGreaterThanOrEqual(4)
      expect(result.metrics.capabilitiesByName["recall_history"] ?? 0).toBe(3)
      expect(result.metrics.finalDecision).toBe("Respond")
      // No stuck-loop trace (signature is args-aware; each call is unique).
      expect(result.metrics.traces.some((t) => /stuck-loop:/.test(t))).toBe(false)
      expect(result.painPoints.some((p) => p.severity === "issue")).toBe(false)
    },
  )
})

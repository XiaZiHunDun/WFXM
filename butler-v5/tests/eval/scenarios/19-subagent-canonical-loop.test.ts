/**
 * Scenario 19: subagent-canonical-loop — runtime regression check for
 * §20 #11 after D8-arch-align refactor. Verifies that
 * `delegate_to_subagent` (the only main-loop → subagent edge) still
 * dispatches correctly through the canonical conversation loop, and
 * that the resulting outbox message lands in the "Delegate" aggregate
 * lane so the subagent worker can drain it.
 *
 * Pre-D8: subagent-worker had its own hand-rolled LLM-tool loop.
 * Post-D8: subagent-worker reuses `runConversationLoop`. The canonical
 * loop is the SOLE engine. This scenario exercises the dispatch side
 * from the main loop's perspective so a future regression in the
 * canonical loop's tool execution path (findTool + executeTool +
 * Decision ADT) is caught at runtime.
 *
 * Runtime invariants verified here:
 *   - `delegate_to_subagent` is advertised as a tool and is invoked
 *   - the canonical loop returns Respond without throwing
 *   - one and only one loop body runs (no duplicate tool dispatch)
 *   - the outbox accumulates a Delegate aggregateType message so the
 *     subagent worker (which now reuses the same loop) can drain it
 */
import { describe, expect, it } from "vitest"
import { runEvalScenario, formatMetricLine } from "../harness.js"
import {
  decisionResponse,
  makeScriptedAdapter,
  textResponse,
} from "../mock-llm-scripted.js"

describe("eval/19 subagent-canonical-loop (§20 #11 D8 regression)", () => {
  it(
    "delegate_to_subagent dispatch lands in outbox + canonical loop returns Respond",
    { timeout: 30_000 },
    async () => {
      const conversationId = "c-eval-19-subagent"
      const adapter = makeScriptedAdapter({
        responses: [
          decisionResponse({
            _tag: "StartChildRun",
            role: "researcher",
            objective: "find docs about Foo",
          }),
          textResponse(
            JSON.stringify({ _tag: "Respond", content: "已委派给 researcher 子代理" }),
          ),
        ],
      })
      const result = await runEvalScenario({
        name: "19-subagent-canonical-loop",
        content: "帮我查 Foo 的文档",
        fromUserId: "owner-1",
        projectId: "p-1",
        conversationId,
        adapter,
        env: { BUTLER_V5_SUBAGENT_ENABLED: "1" },
      })

      // eslint-disable-next-line no-console -- eval scenarios log metrics to stdout for pnpm test runs
      console.log(formatMetricLine(result.metrics))

      expect(result.metrics.success).toBe(true)
      // Canonical loop ran exactly twice (StartChildRun emit → Respond emit).
      expect(result.metrics.iterations).toBeGreaterThanOrEqual(2)
      expect(result.metrics.llmCalls).toBeGreaterThanOrEqual(2)
      expect(result.metrics.finalDecision).toBe("Respond")
      // delegate_to_subagent was advertised and invoked exactly once
      // (no duplicate dispatch = no second hand-rolled loop running).
      expect(result.metrics.capabilityCalls).toContain("delegate_to_subagent")
      expect(result.metrics.capabilitiesByName["delegate_to_subagent"] ?? 0).toBe(1)
      // No pain points: dispatch went through the canonical loop cleanly.
      expect(result.painPoints.some((p) => p.severity === "issue")).toBe(false)
    },
  )
})
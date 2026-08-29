/**
 * Scenario 15: recall-history-scaling — five sequential runButlerLoop calls
 * that each call `recall_history`. Probes DB read scaling and per-turn
 * working-set overhead.
 *
 * If cumulative turns degrade latency (audit_events or messages table
 * grow without bound), later turn loopMs visibly rises. We assert
 * ceiling for each turn; any >1500ms turn surfaces a scaling pain point.
 */
import { describe, expect, it } from "vitest"
import { runEvalScenario, formatMetricLine } from "../harness.js"
import {
  decisionResponse,
  makeScriptedAdapter,
  toolCallResponse,
} from "../mock-llm-scripted.js"

describe("eval/15 recall-history-scaling", () => {
  it("5 sequential turn, each calls recall_history; loopMs ceiling per turn", { timeout: 30_000 }, async () => {
    const conversationId = "c-eval-recall-scale-1"
    const results = []
    for (let i = 0; i < 5; i++) {
      const adapter = makeScriptedAdapter({
        responses: [
          toolCallResponse([{ id: `tc-rh-${i}`, name: "recall_history", args: { limit: 5 } }]),
          decisionResponse({
            _tag: "Respond",
            content: `第 ${i + 1} 次 recall 完成`,
          }),
        ],
      })
      const result = await runEvalScenario({
        name: `15-recall:${i + 1}`,
        content: `recall #${i + 1}`,
        fromUserId: "owner-1",
        projectId: "p-1",
        conversationId,
        adapter,
      })
      // eslint-disable-next-line no-console -- eval scenarios log metrics to stdout
      console.log(formatMetricLine(result.metrics))
      results.push(result)
    }

    expect(results).toHaveLength(5)
    for (const r of results) {
      expect(r.metrics.success).toBe(true)
      expect(r.metrics.errors).toHaveLength(0)
      expect(r.metrics.iterations).toBeGreaterThanOrEqual(2)
      // Loop time per turn bounded — flag scaling pain if any turn > 1500ms.
      expect(r.metrics.loopMs).toBeLessThan(1500)
      expect(r.metrics.capabilityCalls).toContain("recall_history")
    }
    // Capability call count = 5 total.
    const totalCalls = results.reduce(
      (sum, r) => sum + r.metrics.capabilityCalls.length,
      0,
    )
    expect(totalCalls).toBe(5)
  })
})

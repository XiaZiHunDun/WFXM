/**
 * Scenario 06: cycle-tool-cap — LLM repeatedly asks for the same tool
 * (gate for time-capability) until the conversation loop exhausts its
 * iteration budget (5).
 *
 * Expected pain points:
 *   - loop-exhausted (warning) — iter ≥ 5
 *   - tool-retry (warning) — get_current_time×5 ≥ 3 threshold
 *
 * This surfaces the architecture question: should the loop detect
 * "same capability N times with same args" and short-circuit?
 */
import { describe, expect, it } from "vitest"
import { runEvalScenario, formatMetricLine } from "../harness.js"
import { makeScriptedAdapter, toolCallResponse } from "../mock-llm-scripted.js"

describe("eval/06 cycle-tool-cap", () => {
  it("LLM cycles get_current_time 5x → loop exhausts", async () => {
    const adapter = makeScriptedAdapter({
      responses: [
        toolCallResponse([{ id: "tc-1", name: "get_current_time", args: {} }]),
        toolCallResponse([{ id: "tc-2", name: "get_current_time", args: {} }]),
        toolCallResponse([{ id: "tc-3", name: "get_current_time", args: {} }]),
        toolCallResponse([{ id: "tc-4", name: "get_current_time", args: {} }]),
        toolCallResponse([{ id: "tc-5", name: "get_current_time", args: {} }]),
      ],
    })
    const result = await runEvalScenario({
      name: "06-cycle-tool-cap",
      content: "现在几点了",
      fromUserId: "owner-1",
      projectId: "p-1",
      adapter,
    })

    // eslint-disable-next-line no-console -- eval scenarios log metrics to stdout
    console.log(formatMetricLine(result.metrics))

    expect(result.metrics.iterations).toBeGreaterThanOrEqual(5)
    expect(result.metrics.capabilitiesByName["get_current_time"] ?? 0).toBeGreaterThanOrEqual(3)
    const categories = result.painPoints.map((p) => p.category)
    expect(categories).toContain("loop-exhausted")
    expect(categories).toContain("tool-retry")
  })
})

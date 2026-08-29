/**
 * Scenario 06: cycle-tool-cap — LLM repeatedly asks for the same tool
 * (get_current_time) with the same args. After Phase D fix B-06, the
 * conversation-loop detects the same (name, args) signature at threshold
 * 3 and short-circuits with a descriptive trace.
 *
 * Expectations:
 *   - iter ≈ 3 (not 5) — stuck-loop fires earlier than loop-exhausted
 *   - decision = "Finish" with reason "stuck-loop: ..."
 *   - trace contains "stuck-loop: get_current_time invoked 3x with same args; aborting"
 *   - detection is informational (info pain), not warning
 */
import { describe, expect, it } from "vitest"
import { runEvalScenario, formatMetricLine } from "../harness.js"
import { makeScriptedAdapter, toolCallResponse } from "../mock-llm-scripted.js"

describe("eval/06 cycle-tool-cap", () => {
  it("LLM cycles get_current_time 5x with same args → stuck-loop fires at 3", async () => {
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

    expect(result.metrics.iterations).toBe(3)
    // 3rd call short-circuits before tool execution — only 2 tool results emitted.
    expect(result.metrics.capabilitiesByName["get_current_time"] ?? 0).toBe(2)
    expect(result.metrics.finalDecision).toBe("Finish")
    // Stuck-loop trace should be present.
    expect(
      result.metrics.traces.some((t) => /stuck-loop: get_current_time invoked 3x with same args; aborting/.test(t)),
    ).toBe(true)
    // Detection categorized as info (not warning/issue).
    const categories = result.painPoints.map((p) => p.category)
    expect(categories).toContain("stuck-loop")
    expect(result.painPoints.some((p) => p.severity === "issue")).toBe(false)
  })
})

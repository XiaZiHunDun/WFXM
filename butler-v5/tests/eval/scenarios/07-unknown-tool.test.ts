/**
 * Scenario 07: unknown-tool — LLM emits a tool_call for a tool that
 * doesn't exist (e.g. hallucinated capability name).
 *
 * Expected behavior: loop pushes "[error] unknown tool: X" as tool result,
 * continues to next iter, eventually settles on Respond.
 *
 * Expected pain points:
 *   - info-level slow loop not expected here
 *   - this scenario is a probe for whether butler crashes or panics on
 *     unknown tools (it should recover gracefully).
 */
import { describe, expect, it } from "vitest"
import { runEvalScenario, formatMetricLine } from "../harness.js"
import { makeScriptedAdapter, toolCallResponse, textResponse } from "../mock-llm-scripted.js"

describe("eval/07 unknown-tool", () => {
  it("LLM emits tool_call for non-existent tool → loop recovers with Respond", async () => {
    const adapter = makeScriptedAdapter({
      responses: [
        toolCallResponse([
          { id: "tc-1", name: "definitely_does_not_exist", args: { foo: "bar" } },
        ]),
        textResponse(
          JSON.stringify({
            _tag: "Respond",
            content: "抱歉，那个工具我手上没。",
          }),
        ),
      ],
    })
    const result = await runEvalScenario({
      name: "07-unknown-tool",
      content: "请用 definitely_does_not_exist 做点事",
      fromUserId: "owner-1",
      projectId: "p-1",
      adapter,
    })

    // eslint-disable-next-line no-console -- eval scenarios log metrics to stdout
    console.log(formatMetricLine(result.metrics))

    expect(result.metrics.success).toBe(true)
    expect(result.metrics.iterations).toBe(2)
    expect(result.metrics.finalDecision).toBe("Respond")
    expect(result.metrics.reply).toContain("抱歉")
    // No pain points expected: graceful fallback.
    expect(
      result.painPoints.filter((p) => p.severity === "warning" || p.severity === "issue"),
    ).toHaveLength(0)
  })
})

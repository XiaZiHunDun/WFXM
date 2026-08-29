/**
 * Scenario 08: malformed-decision — LLM emits text that LOOKS like a
 * Decision JSON payload but is malformed (truncated mid-value).
 *
 * Decoder path: decodeDecision tries JSON.parse (fail) → embedded
 * extraction (none) → markdown fence / trailing-comma / single-quote repair
 * (still fail) → returns ok:false with reason "invalid JSON".
 *
 * Loop falls through: decode-failed → Respond with raw text.
 *
 * Expected pain points:
 *   - decision-decode-fail (warning) — decoder couldn't recover
 *
 * The trace "decode failed (...); plain-text reply" should appear.
 */
import { describe, expect, it } from "vitest"
import { runEvalScenario, formatMetricLine } from "../harness.js"
import { makeScriptedAdapter, toolCallResponse, textResponse } from "../mock-llm-scripted.js"

describe("eval/08 malformed-decision", () => {
  it("LLM emits truncated JSON → decoder fails → plain-text Respond", async () => {
    // First iter: legitimate tool call; second iter: truncated Decision JSON.
    const adapter = makeScriptedAdapter({
      responses: [
        toolCallResponse([{ id: "tc-1", name: "get_current_time", args: {} }]),
        textResponse('{"_tag":"Respond","content":"hi'),  // truncated
      ],
    })
    const result = await runEvalScenario({
      name: "08-malformed-decision",
      content: "现在几点了",
      fromUserId: "owner-1",
      projectId: "p-1",
      adapter,
    })

    // eslint-disable-next-line no-console -- eval scenarios log metrics to stdout
    console.log(formatMetricLine(result.metrics))

    expect(result.metrics.success).toBe(true)
    expect(result.metrics.iterations).toBeGreaterThanOrEqual(2)
    const categories = result.painPoints.map((p) => p.category)
    expect(categories).toContain("decision-decode-fail")
    // The trace should mention "decode failed".
    expect(result.metrics.traces.some((t) => /decode failed/i.test(t))).toBe(true)
  })
})

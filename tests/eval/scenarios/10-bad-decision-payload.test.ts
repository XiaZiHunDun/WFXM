/**
 * Scenario 10: bad-decision-payload — LLM emits a Decision JSON with
 * missing required field (e.g. CallCapability without `name`). The
 * decoder's parseModelDecisionObject returns ok:false with the specific
 * reason "CallCapability.name must be string".
 *
 * Loop falls through to plain-text Respond.
 *
 * Expected pain points:
 *   - decision-decode-fail (warning) — discriminator accepts JSON but
 *     payload is invalid
 *
 * Architecture question: should the LLM receive structured feedback
 * (e.g. "name required") so it can self-correct, or is the fail-quiet
 * plain-text fallback the intended contract? Today: fail-quiet.
 */
import { describe, expect, it } from "vitest"
import { runEvalScenario, formatMetricLine } from "../harness.js"
import { makeScriptedAdapter, textResponse } from "../mock-llm-scripted.js"

describe("eval/10 bad-decision-payload", () => {
  it("Decision JSON missing required field → decode fail → plain-text Respond", async () => {
    const adapter = makeScriptedAdapter({
      responses: [
        textResponse(
          JSON.stringify({
            _tag: "CallCapability",
            // missing `name`
            arguments: { foo: "bar" },
          }),
        ),
      ],
    })
    const result = await runEvalScenario({
      name: "10-bad-decision-payload",
      content: "做点什么",
      fromUserId: "owner-1",
      projectId: "p-1",
      adapter,
    })

    // eslint-disable-next-line no-console -- eval scenarios log metrics to stdout
    console.log(formatMetricLine(result.metrics))

    const categories = result.painPoints.map((p) => p.category)
    expect(categories).toContain("decision-decode-fail")
    // Plain-text Respond carried forward.
    expect(result.metrics.reply).toMatch(/name must be string|CallCapability/)
  })
})

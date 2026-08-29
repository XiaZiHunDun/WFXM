/**
 * Scenario 18: decoder-retry-success — Phase D fix B-08/10 verification.
 *
 * LLM emits a Decision JSON with missing required field on iter 1, then
 * a valid Decision Respond on iter 2. The conversation-loop's decoder-
 * feedback retry path should fire: iter 1 fail → push user-message
 * feedback → iter 2 succeeds → final Respond.
 *
 * This validates the LLM self-correction workflow surfaced by Phase B
 * eval findings B-08/B-10. Owner sees the corrected reply, not a stub.
 */
import { describe, expect, it } from "vitest"
import { runEvalScenario, formatMetricLine } from "../harness.js"
import {
  decisionResponse,
  makeScriptedAdapter,
} from "../mock-llm-scripted.js"

describe("eval/18 decoder-retry-success (B-08/10 fix verification)", () => {
  it("LLM emits bad JSON then valid JSON → retry succeeds with Respond", async () => {
    const adapter = makeScriptedAdapter({
      responses: [
        // iter 1: missing `name` field — decoder rejects with reason "CallCapability.name must be string"
        decisionResponse({
          _tag: "CallCapability",
          arguments: { foo: "bar" },
        }),
        // iter 2: LLM self-corrects after seeing the feedback message
        decisionResponse({ _tag: "Respond", content: "修正后的回复" }),
      ],
    })
    const result = await runEvalScenario({
      name: "18-decoder-retry-success",
      content: "做点什么",
      fromUserId: "owner-1",
      projectId: "p-1",
      adapter,
    })

    // eslint-disable-next-line no-console -- eval scenarios log metrics to stdout
    console.log(formatMetricLine(result.metrics))

    expect(result.metrics.success).toBe(true)
    expect(result.metrics.iterations).toBeGreaterThanOrEqual(2)
    expect(result.metrics.finalDecision).toBe("Respond")
    // Owner sees the corrected content, not the parse error / not a stub.
    expect(result.metrics.reply).toBe("修正后的回复")
    // Trace must surface the retry attempt (decode failed retry 1/1: ...).
    expect(
      result.metrics.traces.some((t) =>
        /decode failed retry 1\/1: CallCapability\.name must be string/.test(t),
      ),
    ).toBe(true)
    // Total decode-decode-fail pain point remains — the first attempt failed.
    expect(result.painPoints.map((p) => p.category)).toContain("decision-decode-fail")
    // No loop-exhausted or stuck-loop — self-correction succeeded quickly.
    expect(
      result.painPoints.some(
        (p) => p.severity === "warning" && (p.category === "loop-exhausted" || p.category === "tool-retry"),
      ),
    ).toBe(false)
  })
})

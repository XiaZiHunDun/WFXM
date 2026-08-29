/**
 * Scenario 13: cross-conversation-parallel — three distinct conversations,
 * each running their own runButlerLoop call in parallel against ONE wiring.
 *
 * Expectations:
 *   - All three succeed independently (no cross-conversation interference)
 *   - Each iterates ≥ 2 (one capability + final Respond)
 *   - Each finalDecision = "Respond"
 *   - wallClockMs ≈ max(per-call) ≈ parallel-equivalent, far below sum
 *
 * Pain heuristic: 0 expected (per-conversation lock is correct design).
 */
import { describe, expect, it } from "vitest"
import { runEvalConcurrent, formatMetricLine } from "../harness.js"
import {
  decisionResponse,
  makeScriptedAdapter,
  toolCallResponse,
} from "../mock-llm-scripted.js"

describe("eval/13 cross-conversation-parallel", () => {
  it("3 conversations × 1 turn each, runButlerLoop in parallel", { timeout: 30_000 }, async () => {
    const makeInputs = () =>
      ["a", "b", "c"].map((tag, _idx) => {
        const toolCallResponses = [
          toolCallResponse([{ id: `tc-${tag}`, name: "get_current_time", args: {} }]),
          decisionResponse({
            _tag: "Respond",
            content: `conversation ${tag} done`,
          }),
        ]
        const adapter = makeScriptedAdapter({ responses: toolCallResponses })
        return {
          name: `13-cross-conv-${tag}`,
          content: `conv ${tag}: 现在几点了`,
          fromUserId: "owner-1",
          projectId: "p-1",
          conversationId: `c-eval-parallel-${tag}`,
          adapter,
        }
      })

    const { results, wallClockMs } = await runEvalConcurrent(
      "13-cross-conversation-parallel",
      makeInputs(),
    )

    for (const result of results) {
      // eslint-disable-next-line no-console -- eval scenarios log metrics to stdout
      console.log(formatMetricLine(result.metrics))
      expect(result.metrics.success).toBe(true)
      expect(result.metrics.iterations).toBeGreaterThanOrEqual(2)
      expect(result.metrics.finalDecision).toBe("Respond")
      expect(result.metrics.reply).toMatch(/done/)
    }
    // Sanity: should be parallelized, not 3× sequential.
    expect(wallClockMs).toBeLessThan(15_000)
  })
})

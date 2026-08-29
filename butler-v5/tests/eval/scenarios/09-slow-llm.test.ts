/**
 * Scenario 09: slow-llm — LLM takes 1500ms per call. With 2 iterations
 * (tool_call + Respond) this scenario should take ≥ 3s of loop time.
 *
 * Expected pain points:
 *   - slow-loop (info) — loopMs > 2000 with ≤2 iterations
 *
 * Architecture question: does the conversation loop have a per-LLM-call
 * timeout? If not, a misbehaving/slow LLM can stall owner waits indefinitely.
 * This scenario surfaces that missing bound.
 */
import { describe, expect, it } from "vitest"
import { runEvalScenario, formatMetricLine } from "../harness.js"
import { makeScriptedAdapter, toolCallResponse, textResponse } from "../mock-llm-scripted.js"

describe("eval/09 slow-llm", () => {
  // latencyMs=1500 × 2 iter + setup; default 10s testTimeout is too tight under
  // full-suite contention (vitest harness runs many ~1s DB-init scenarios in parallel).
  it("LLM latencyMs=1500 × 2 iters → loop > 3s → slow-loop info pain", { timeout: 30_000 }, async () => {
    const adapter = makeScriptedAdapter({
      latencyMs: 1500,
      responses: [
        toolCallResponse([{ id: "tc-1", name: "get_current_time", args: {} }]),
        textResponse(
          JSON.stringify({ _tag: "Respond", content: "现在 14:30" }),
        ),
      ],
    })
    const result = await runEvalScenario({
      name: "09-slow-llm",
      content: "现在几点了",
      fromUserId: "owner-1",
      projectId: "p-1",
      adapter,
    })

    // eslint-disable-next-line no-console -- eval scenarios log metrics to stdout
    console.log(formatMetricLine(result.metrics))

    expect(result.metrics.success).toBe(true)
    expect(result.metrics.iterations).toBe(2)
    // Loop time must reflect at least the LLM delay (cumulative adapter sleep).
    expect(result.metrics.loopMs).toBeGreaterThanOrEqual(2500)
    const categories = result.painPoints.map((p) => p.category)
    expect(categories).toContain("slow-loop")
  })
})

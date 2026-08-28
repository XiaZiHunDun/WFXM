/**
 * Scenario 04: owner asks for prior conversation history; LLM emits
 * native tool_call to recall_history. The capability may return empty
 * (cold conversation) — we only assert the flow: capability invoked,
 * loop completed to Respond, no pain points.
 */
import { describe, expect, it } from "vitest"
import { runEvalScenario, formatMetricLine } from "../harness.js"
import {
  makeScriptedAdapter,
  textResponse,
  toolCallResponse,
} from "../mock-llm-scripted.js"

describe("eval/04 recall-history (native tool call)", () => {
  it("owner: '昨天聊了什么' → LLM calls recall_history → Respond with summary", async () => {
    const adapter = makeScriptedAdapter({
      responses: [
        toolCallResponse([
          { id: "tc-1", name: "recall_history", args: { limit: 20 } },
        ]),
        textResponse(
          JSON.stringify({
            _tag: "Respond",
            content: "昨天主要聊了 Foo 的实现细节。",
          }),
        ),
      ],
    })
    const result = await runEvalScenario({
      name: "04-recall-history",
      content: "昨天聊了什么",
      fromUserId: "owner-1",
      projectId: "p-1",
      adapter,
    })

    // eslint-disable-next-line no-console -- eval scenarios log metrics to stdout for pnpm test runs
    console.log(formatMetricLine(result.metrics))

    expect(result.metrics.success).toBe(true)
    expect(result.metrics.iterations).toBeGreaterThanOrEqual(2)
    expect(result.metrics.capabilityCalls).toContain("recall_history")
    expect(result.metrics.finalDecision).toBe("Respond")
    expect(result.painPoints.filter((p) => p.severity !== "info")).toHaveLength(0)
  })
})

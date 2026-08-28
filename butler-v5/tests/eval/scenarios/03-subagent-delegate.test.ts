/**
 * Scenario 03: owner requests a delegated subagent task. LLM emits
 * StartChildRun JSON-decision with role + objective. Loop dispatches
 * delegate_to_subagent (via conversation-loop's tool-call wrap).
 *
 * NOTE: this scenario uses BUTLER_V5_SUBAGENT_ENABLED=1 to enable the
 * subagent worker. The exec subagent worker may fail to spin up if no
 * LLM creds exist; we treat that as a captured error rather than panic.
 */
import { describe, expect, it } from "vitest"
import { runEvalScenario, formatMetricLine } from "../harness.js"
import { makeScriptedAdapter, decisionResponse, textResponse } from "../mock-llm-scripted.js"

describe("eval/03 subagent-delegate (StartChildRun JSON-decision)", () => {
  it("owner: '帮我委派' → LLM emits StartChildRun → loop dispatches delegate_to_subagent", async () => {
    const adapter = makeScriptedAdapter({
      responses: [
        decisionResponse({
          _tag: "StartChildRun",
          role: "researcher",
          objective: "find docs about Foo",
        }),
        textResponse(
          JSON.stringify({ _tag: "Respond", content: "已委派给 researcher 子代理" }),
        ),
      ],
    })
    const result = await runEvalScenario({
      name: "03-subagent-delegate",
      content: "帮我查 Foo 的文档",
      fromUserId: "owner-1",
      projectId: "p-1",
      adapter,
      env: { BUTLER_V5_SUBAGENT_ENABLED: "1" },
    })

    // eslint-disable-next-line no-console -- eval scenarios log metrics to stdout for pnpm test runs
    console.log(formatMetricLine(result.metrics))

    expect(result.metrics.success).toBe(true)
    expect(result.metrics.iterations).toBeGreaterThanOrEqual(2)
    expect(result.metrics.llmCalls).toBeGreaterThanOrEqual(2)
    expect(result.metrics.finalDecision).toBe("Respond")
    expect(result.metrics.capabilityCalls).toContain("delegate_to_subagent")
  })
})

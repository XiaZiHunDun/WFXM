/**
 * Scenario 02: owner requests a write; LLM emits WaitForApproval (JSON-decision mode).
 * The loop surfaces a RunPauseForApproval with reply including approval id.
 * Expected: 1 LLM call, 0 capability calls (write_file blocked at policy),
 *   finalDecision = "WaitForApproval", reply contains "需要确认".
 */
import { describe, expect, it } from "vitest"
import { runEvalScenario, formatMetricLine } from "../harness.js"
import { makeScriptedAdapter, decisionResponse } from "../mock-llm-scripted.js"

describe("eval/02 write-file-approval (WaitForApproval JSON-decision)", () => {
  it("owner: '写个文件' → LLM emits WaitForApproval → loop surfaces approval prompt", async () => {
    const adapter = makeScriptedAdapter({
      responses: [
        decisionResponse({
          _tag: "WaitForApproval",
          question: "OK to write /ws/notes.txt with 'hello world'?",
        }),
      ],
    })
    const result = await runEvalScenario({
      name: "02-write-file-approval",
      content: "帮我写 /ws/notes.txt 内容是 hello world",
      fromUserId: "owner-1",
      projectId: "p-1",
      adapter,
    })

    // eslint-disable-next-line no-console -- eval scenarios log metrics to stdout for pnpm test runs
    console.log(formatMetricLine(result.metrics))

    expect(result.metrics.success).toBe(true)
    expect(result.metrics.llmCalls).toBe(1)
    expect(result.metrics.iterations).toBe(1)
    expect(result.metrics.finalDecision).toBe("WaitForApproval")
    expect(result.metrics.reply).toContain("需要确认")
    expect(result.metrics.capabilityCalls).toHaveLength(0)
    expect(result.painPoints.filter((p) => p.severity !== "info")).toHaveLength(0)
  })
})

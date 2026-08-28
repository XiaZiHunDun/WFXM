/**
 * Scenario 01: owner reads a workspace file via native tool_call.
 * Expected: 2 LLM calls (initial tool_call + final Respond), 1 capability call,
 *   no pain points.
 */
import { describe, expect, it } from "vitest"
import { runEvalScenario, formatMetricLine } from "../harness.js"
import {
  makeScriptedAdapter,
  textResponse,
  toolCallResponse,
} from "../mock-llm-scripted.js"

describe("eval/01 read-file (happy path, native tool call)", () => {
  it("owner: '读 /ws/README.md' → LLM calls read_file → final Respond", async () => {
    const adapter = makeScriptedAdapter({
      responses: [
        toolCallResponse([
          { id: "tc-1", name: "read_file", args: { path: "/ws/README.md" } },
        ]),
        textResponse(
          JSON.stringify({ _tag: "Respond", content: "文件已读：" }),
        ),
      ],
    })
    const result = await runEvalScenario({
      name: "01-read-file",
      content: "读 /ws/README.md",
      fromUserId: "owner-1",
      projectId: "p-1",
      adapter,
    })

    // eslint-disable-next-line no-console -- eval scenarios log metrics to stdout for pnpm test runs
    console.log(formatMetricLine(result.metrics))

    expect(result.metrics.success).toBe(true)
    expect(result.metrics.iterations).toBeGreaterThanOrEqual(2)
    expect(result.metrics.llmCalls).toBeGreaterThanOrEqual(2)
    expect(result.metrics.capabilityCalls).toContain("read_file")
    expect(result.painPoints.filter((p) => p.severity !== "info")).toHaveLength(0)
  })
})

/**
 * Scenario 16: llm-call-timeout — Phase D fix verification for finding B-09.
 *
 * Scenario: LLM takes 5000ms per call; we set llmTimeoutMs to 200ms.
 * Expected: first iteration's LLM call times out → loop surfaces
 * `{ ok: false, reason: "LLM timeout after 200ms" }` → falls into the
 * existing "llm failure" Finish + stub-reply path with trace.
 *
 * Validates: butler never blocks indefinitely on a hung LLM provider.
 */
import { describe, expect, it } from "vitest"
import { runEvalScenario, formatMetricLine } from "../harness.js"
import {
  makeScriptedAdapter,
  textResponse,
} from "../mock-llm-scripted.js"

describe("eval/16 llm-call-timeout (B-09 fix verification)", () => {
  it("LLM 5000ms latency, llmTimeoutMs=200 → loop surfaces timeout stub", { timeout: 30_000 }, async () => {
    const adapter = makeScriptedAdapter({
      latencyMs: 5000, // way over the 200ms timeout
      responses: [textResponse("")] // never reached
    })
    const result = await runEvalScenario({
      name: "16-llm-call-timeout",
      content: "请回答",
      fromUserId: "owner-1",
      projectId: "p-1",
      adapter,
      llmTimeoutMs: 200,
    })

    // eslint-disable-next-line no-console -- eval scenarios log metrics to stdout
    console.log(formatMetricLine(result.metrics))

    expect(result.metrics.success).toBe(true)
    expect(result.metrics.iterations).toBe(1)
    expect(result.metrics.finalDecision).toBe("Finish")
    // trace must surface the timeout reason
    expect(
      result.metrics.traces.some((t) => /LLM timeout after 200ms/.test(t)),
    ).toBe(true)
    // The reply is the stub (wechat stub fallback) — owner gets "MVP stub reply"
    expect(result.metrics.reply).toContain("MVP stub")
    // Loop ran in ≤ 1s (timeout 200ms + JSDOM overhead)
    expect(result.metrics.loopMs).toBeLessThan(2000)
  })
})

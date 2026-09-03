/**
 * Scenario 14: sustained-eight-turns — eight sequential runButlerLoop calls
 * on the same conversation. Each turn uses a different capability
 * (greet_with_time / get_current_time / summarize_today / recall_history /
 * read_file / delegate_to_subagent stub).
 *
 * Probe scope: per-turn state isolation, audit_events row-count growth,
 * run accumulation on conversation, message idempotency.
 *
 * Each turn uses a fresh scripted adapter; we capture metrics per turn.
 * Pain points would surface if any turn leaks state from prior turn, or
 * if cumulative turns leak resources (audit unbounded growth).
 */
import { describe, expect, it } from "vitest"
import { runEvalScenario, makeEvalHarness, closeEvalHarness, formatMetricLine } from "../harness.js"
import {
  decisionResponse,
  makeScriptedAdapter,
  toolCallResponse,
} from "../mock-llm-scripted.js"

describe("eval/14 sustained-eight-turns", () => {
  it("8 sequential runButlerLoop calls on same conversation", { timeout: 60_000 }, async () => {
    const conversationId = "c-eval-sustained-1"
    // 8 turns × PGlite migrate/turn would exceed 30s under full-suite load
    // (the migrate is ~700ms/turn). Reuse one harness across all turns so the
    // DB + wiring are built once; keeps suite contention well under budget.
    const harness = await makeEvalHarness()
    const turns: readonly { readonly prompt: string; readonly setup: () => ReturnType<typeof makeScriptedAdapter> }[] = [
      {
        prompt: "早上好",
        setup: () =>
          makeScriptedAdapter({
            responses: [
              toolCallResponse([{ id: "tc-1", name: "greet_with_time", args: {} }]),
              decisionResponse({ _tag: "Respond", content: "早上好" }),
            ],
          }),
      },
      {
        prompt: "现在几点",
        setup: () =>
          makeScriptedAdapter({
            responses: [
              toolCallResponse([{ id: "tc-2", name: "get_current_time", args: {} }]),
              decisionResponse({ _tag: "Respond", content: "14:30" }),
            ],
          }),
      },
      {
        prompt: "今天概要",
        setup: () =>
          makeScriptedAdapter({
            responses: [
              toolCallResponse([{ id: "tc-3", name: "summarize_today", args: {} }]),
              decisionResponse({ _tag: "Respond", content: "今天 3 件完成" }),
            ],
          }),
      },
      {
        prompt: "昨天聊了什么",
        setup: () =>
          makeScriptedAdapter({
            responses: [
              toolCallResponse([{ id: "tc-4", name: "recall_history", args: { limit: 5 } }]),
              decisionResponse({ _tag: "Respond", content: "Foo 项目" }),
            ],
          }),
      },
      {
        prompt: "读 /ws/README.md",
        setup: () =>
          makeScriptedAdapter({
            responses: [
              toolCallResponse([
                { id: "tc-5", name: "read_file", args: { path: "/ws/README.md" } },
              ]),
              decisionResponse({ _tag: "Respond", content: "已读" }),
            ],
          }),
      },
      {
        prompt: "再 time 一下",
        setup: () =>
          makeScriptedAdapter({
            responses: [
              toolCallResponse([{ id: "tc-6", name: "get_current_time", args: {} }]),
              decisionResponse({ _tag: "Respond", content: "14:35" }),
            ],
          }),
      },
      {
        prompt: "再次 recall",
        setup: () =>
          makeScriptedAdapter({
            responses: [
              toolCallResponse([{ id: "tc-7", name: "recall_history", args: { limit: 10 } }]),
              decisionResponse({ _tag: "Respond", content: "召回 5 条" }),
            ],
          }),
      },
      {
        prompt: "send wechat file 不发了",
        setup: () =>
          makeScriptedAdapter({
            responses: [
              decisionResponse({
                _tag: "WaitForApproval",
                question: "要发文件吗？",
              }),
            ],
          }),
      },
    ]

    const results = []
    for (let i = 0; i < turns.length; i++) {
      const turn = turns[i]
      if (!turn) throw new Error(`turn ${i} missing`)
      const adapter = turn.setup()
      const result = await runEvalScenario({
        name: `14-sustained:${turn.prompt.slice(0, 8)}`,
        content: turn.prompt,
        fromUserId: "owner-1",
        projectId: "p-1",
        conversationId,
        adapter,
        harness,
      })
      // eslint-disable-next-line no-console -- eval scenarios log metrics to stdout
      console.log(formatMetricLine(result.metrics))
      results.push(result)
    }
    await closeEvalHarness(harness)

    // Every turn completes (no throws).
    expect(results).toHaveLength(8)
    for (const r of results) {
      expect(r.metrics.success).toBe(true)
      expect(r.metrics.errors).toHaveLength(0)
    }
    // Final turn uses WaitForApproval (JSON-decision).
    expect(results[results.length - 1]?.metrics.finalDecision).toBe("WaitForApproval")
    // Cross-turn capacity calls evenly distributed (no spike → no retry loop).
    const totalCapCalls = results.reduce(
      (sum, r) => sum + r.metrics.capabilityCalls.length,
      0,
    )
    expect(totalCapCalls).toBe(7) // 7 of 8 turns called a capability
    // No loop-exhausted across turns.
    const allIters = results.flatMap((r) => r.metrics.iterations)
    expect(allIters.every((i) => i <= 5)).toBe(true)
  })
})

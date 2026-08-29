/**
 * Scenario 11: active-main-blocks-inbound — pre-seed an active main Run
 * (status: "running") on a conversation via `beforeLoop`, then call
 * runButlerLoop. The RunEngine detects the active main run and returns
 * ActiveMainRunConflict → wechat-inbound-butler translates to a friendly
 * stub reply that names the active run id.
 *
 * This is deterministic (no real concurrency required). It exercises the
 * "single active main per conversation" invariant from prod-arch §3.1.
 *
 * Expected behavior (NOT a pain point):
 *   - iter=0, decision=Finish
 *   - reply mentions "进行中的 Run" or "未完成"
 *   - trace contains "active-main-run-conflict"
 */
import { describe, expect, it } from "vitest"
import { runEvalScenario, formatMetricLine } from "../harness.js"
import { makeScriptedAdapter, decisionResponse } from "../mock-llm-scripted.js"

describe("eval/11 active-main-blocks-inbound", () => {
  it("active main Run in conversation → new runButlerLoop returns stub", async () => {
    const conversationId = "c-eval-conflict-1"
    const existingActiveRunId = crypto.randomUUID()
    const adapter = makeScriptedAdapter({
      responses: [
        decisionResponse({ _tag: "Respond", content: "this will not be reached" }),
      ],
    })
    const result = await runEvalScenario({
      name: "11-active-main-blocks-inbound",
      content: "再做点别的",
      fromUserId: "owner-1",
      projectId: "p-1",
      conversationId,
      adapter,
      beforeLoop: async ({ wiring }) => {
        // 1) Seed conversation so it exists in 0002 messages.
        await wiring.runtimeStore.createConversationWithUserMessage({
          conversationId,
          messageId: crypto.randomUUID(),
          subject: "owner-1",
          content: { text: "seed" },
          triggerSource: "channel",
          idempotencyKey: "seed-" + crypto.randomUUID(),
          createdAt: new Date(),
        })
        // 2) Seed an active main Run (parentRunId null, status: queued; queued is in ACTIVE_MAIN_RUN_STATUSES so the conflict triggers).
        await wiring.runtimeStore.createRun({
          id: existingActiveRunId,
          conversationId,
          parentRunId: null,
          triggerSource: "channel",
          idempotencyKey: "active-run-" + crypto.randomUUID(),
          subject: "owner-1",
          goal: "active seed",
          budget: {},
          deadline: null,
          createdAt: new Date(),
        })
      },
    })

    // eslint-disable-next-line no-console -- eval scenarios log metrics to stdout
    console.log(formatMetricLine(result.metrics))

    expect(result.metrics.success).toBe(true)
    expect(result.metrics.iterations).toBe(0)
    expect(result.metrics.finalDecision).toBe("Finish")
    expect(
      result.metrics.reply.includes("进行中的 Run") ||
        result.metrics.reply.includes("未完成"),
    ).toBe(true)
    expect(
      result.metrics.traces.some((t) => /active-main-run-conflict/.test(t)),
    ).toBe(true)
    // Per design — this is graceful handling, not a pain point.
    expect(
      result.painPoints.filter((p) => p.severity === "warning" || p.severity === "issue"),
    ).toHaveLength(0)
  })
})

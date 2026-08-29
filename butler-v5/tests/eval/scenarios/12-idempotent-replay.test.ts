/**
 * Scenario 12: idempotent-replay — call `runtimeStore.createConversationWithUserMessage`
 * twice with the same `idempotencyKey` inside a single `beforeLoop`. The
 * second call must return the existing messageId (UNIQUE constraint dedup
 * in `messages.idempotency_key`).
 *
 * Probe scope: dedup path inside a single DB / single wiring. We deliberately
 * call the store API directly so the test does not depend on LLM behavior.
 */
import { describe, expect, it } from "vitest"
import { runEvalScenario, formatMetricLine } from "../harness.js"
import { makeScriptedAdapter, decisionResponse } from "../mock-llm-scripted.js"

describe("eval/12 idempotent-replay", () => {
  it("same idempotencyKey twice → second call returns existing messageId", async () => {
    const conversationId = "c-eval-idem-1"
    const idempotencyKey = "shared-key-" + crypto.randomUUID()
    const firstMessageIdInput = crypto.randomUUID()
    const secondMessageIdInput = crypto.randomUUID()
    const adapter = makeScriptedAdapter({
      responses: [
        decisionResponse({ _tag: "Respond", content: "ok" }),
      ],
    })
    let firstResult = ""
    let secondResult = ""
    const result = await runEvalScenario({
      name: "12-idempotent-replay",
      content: "first message",
      fromUserId: "owner-1",
      projectId: "p-1",
      conversationId,
      adapter,
      beforeLoop: async ({ wiring }) => {
        const first = await wiring.runtimeStore.createConversationWithUserMessage({
          conversationId,
          messageId: firstMessageIdInput,
          subject: "owner-1",
          content: { text: "first" },
          triggerSource: "channel",
          idempotencyKey,
          createdAt: new Date(),
        })
        firstResult = first.messageId
        const dup = await wiring.runtimeStore.createConversationWithUserMessage({
          conversationId,
          messageId: secondMessageIdInput, // would insert if dedup fails
          subject: "owner-1",
          content: { text: "second" },
          triggerSource: "channel",
          idempotencyKey, // SAME key — expect existing messageId
          createdAt: new Date(),
        })
        secondResult = dup.messageId
      },
    })

    // eslint-disable-next-line no-console -- eval scenarios log metrics to stdout
    console.log(formatMetricLine(result.metrics))

    expect(result.metrics.success).toBe(true)
    expect(firstResult).toBe(firstMessageIdInput)
    expect(secondResult).toBe(firstMessageIdInput) // dedup returned the existing
  })
})

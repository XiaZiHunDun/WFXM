/**
 * Scenario 15: recall-history-scaling — five sequential runButlerLoop calls
 * that each call `recall_history`. Probes DB read scaling and per-turn
 * working-set overhead.
 *
 * If cumulative turns degrade latency (audit_events or messages table
 * grow without bound), later turn loopMs visibly rises. We assert
 * a ceiling for each turn, plus the per-turn delta that is what this
 * scenario is actually for.
 *
 * D82 T1: the original 1500ms absolute ceiling was written when a
 * turn cost 19-71ms, so it had ~20x headroom. Since D71/D64 the tool
 * execution throat carries a fatigue cooldown sleep
 * (`wechat-inbound-butler.ts` awaits `DEFAULT_COOLDOWN_MS` inline
 * once the audit-event count crosses the signal threshold), so every
 * turn after the first costs a flat ~3s. That is an intended product
 * cost, not scaling pain. The ceiling now tracks the constant so it
 * does not have to be re-tuned whenever the cooldown changes, and the
 * delta assertion below — immune to a constant offset — is what
 * catches genuine per-turn degradation.
 */
import { describe, expect, it } from "vitest"
import { DEFAULT_COOLDOWN_MS } from "@butler/api/lib/fatigue/policy.js"
import { runEvalScenario, makeEvalHarness, closeEvalHarness, formatMetricLine } from "../harness.js"
import { decisionResponse, makeScriptedAdapter, toolCallResponse } from "../mock-llm-scripted.js"

/** Per-turn latency budget excluding the fatigue cooldown the loop pays. */
const LOOP_BUDGET_WITHOUT_COOLDOWN_MS = 1_500
/** Per-turn ceiling = product cooldown + working-set budget above. */
const LOOP_MS_CEILING = DEFAULT_COOLDOWN_MS + LOOP_BUDGET_WITHOUT_COOLDOWN_MS

describe("eval/15 recall-history-scaling", () => {
  // 5 turns; reuse one harness so the PGlite migrate runs once instead of
  // per turn (keeps suite contention well within the timeout budget).
  it(
    "5 sequential turn, each calls recall_history; loopMs ceiling per turn",
    { timeout: 60_000 },
    async () => {
      const conversationId = "c-eval-recall-scale-1"
      const harness = await makeEvalHarness()
      const results = []
      for (let i = 0; i < 5; i++) {
        const adapter = makeScriptedAdapter({
          responses: [
            toolCallResponse([{ id: `tc-rh-${i}`, name: "recall_history", args: { limit: 5 } }]),
            decisionResponse({
              _tag: "Respond",
              content: `第 ${i + 1} 次 recall 完成`,
            }),
          ],
        })
        const result = await runEvalScenario({
          name: `15-recall:${i + 1}`,
          content: `recall #${i + 1}`,
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

      expect(results).toHaveLength(5)
      for (const r of results) {
        expect(r.metrics.success).toBe(true)
        expect(r.metrics.errors).toHaveLength(0)
        expect(r.metrics.iterations).toBeGreaterThanOrEqual(2)
        // Per-turn ceiling — headroom above the flat fatigue cooldown.
        expect(r.metrics.loopMs).toBeLessThan(LOOP_MS_CEILING)
        expect(r.metrics.capabilityCalls).toContain("recall_history")
      }

      // D82 T1: the actual intent of this scenario — cumulative turns must
      // not make each turn progressively more expensive. Measured on the
      // cooldown-adjusted latency so a flat 3s product cost does not
      // mask (or fake) a scaling regression.
      const netLoopMs = results.map((r) => Math.max(0, r.metrics.loopMs - DEFAULT_COOLDOWN_MS))
      for (let i = 1; i < netLoopMs.length; i++) {
        const previous = netLoopMs[i - 1] ?? 0
        const growth = (netLoopMs[i] ?? 0) - previous
        expect(
          growth,
          `turn ${i + 1} net loopMs grew ${growth}ms over turn ${i} ` +
            `(${netLoopMs.join(" → ")}ms after subtracting the ${DEFAULT_COOLDOWN_MS}ms cooldown)`,
        ).toBeLessThanOrEqual(LOOP_BUDGET_WITHOUT_COOLDOWN_MS)
      }

      // Capability call count = 5 total.
      const totalCalls = results.reduce((sum, r) => sum + r.metrics.capabilityCalls.length, 0)
      expect(totalCalls).toBe(5)
    },
  )
})

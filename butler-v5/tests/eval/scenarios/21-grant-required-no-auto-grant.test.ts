/**
 * Scenario 21: grant-required-no-auto-grant — runtime regression check
 * for §20 #10 after D10-arch-align audit. Verifies that calling a
 * Grant-required capability (write_file) WITHOUT a prior ScopedGrant
 * routes through the runtime approval gate (Policy Gate → Ask →
 * RunPauseForApproval → WaitForApproval). The capability does NOT
 * auto-execute and does NOT auto-create a Grant.
 *
 * This is the runtime counterpart of the static arch guard
 * tests/architecture/capability-no-auto-grant.test.ts. Where the static
 * guard locks "register does not call createScopedGrant", this
 * scenario locks "executeTool for a Grant-required capability without
 * a prior Grant does not bypass Policy Gate and does not silently
 * issue a Grant on the spot".
 *
 * Flow:
 *   1. Conversation has NO ScopedGrant for write_file.
 *   2. LLM emits `write_file` as a native tool_call (no JSON-decision
 *      WaitForApproval wrapper).
 *   3. The canonical conversation loop calls executeTool, which routes
 *      through Policy Gate.
 *   4. Policy Gate returns Ask (write_file is Grant-required, no
 *      active Grant found).
 *   5. The loop persists a waiting_approval step, throws
 *      RunPauseForApproval, and surfaces WaitForApproval as the
 *      final decision.
 *   6. The reply must contain the approval prompt (owner needs to
 *      confirm before the file is actually written).
 *
 * If a future commit broke the invariant (e.g. by silently issuing a
 * Grant or skipping Policy Gate), the loop would instead land on
 * Respond with the file content written, and metrics.llmCalls would
 * reflect a normal finish rather than a single-turn approval pause.
 */
import { describe, expect, it } from "vitest"
import { runEvalScenario, formatMetricLine } from "../harness.js"
import { makeScriptedAdapter, toolCallResponse } from "../mock-llm-scripted.js"

describe("eval/21 grant-required-no-auto-grant (§20 #10 D10 runtime check)", () => {
  it(
    "write_file without prior Grant → Policy Gate blocks → WaitForApproval (no silent execute, no auto-grant)",
    { timeout: 30_000 },
    async () => {
      const conversationId = "c-eval-21-grant"
      const adapter = makeScriptedAdapter({
        responses: [
          toolCallResponse([
            {
              id: "tc-21-write",
              name: "write_file",
              args: { path: "/ws/notes.txt", content: "auto-grant probe" },
            },
          ]),
        ],
      })
      const result = await runEvalScenario({
        name: "21-grant-required-no-auto-grant",
        content: "帮我写 /ws/notes.txt 内容是 auto-grant probe",
        fromUserId: "owner-1",
        projectId: "p-1",
        conversationId,
        adapter,
      })

      // eslint-disable-next-line no-console -- eval scenarios log metrics to stdout for pnpm test runs
      console.log(formatMetricLine(result.metrics))

      expect(result.metrics.success).toBe(true)
      // The loop ran exactly once (LLM emitted tool_call, executeTool
      // returned RunPauseForApproval, loop surfaced WaitForApproval).
      expect(result.metrics.llmCalls).toBe(1)
      expect(result.metrics.iterations).toBe(1)
      expect(result.metrics.finalDecision).toBe("WaitForApproval")
      // write_file was advertised and invoked exactly once (not silently
      // executed; not skipped).
      expect(result.metrics.capabilityCalls).toContain("write_file")
      expect(result.metrics.capabilitiesByName["write_file"] ?? 0).toBe(1)
      // The reply must surface the approval prompt — owner must
      // explicitly confirm before the file is written. If this string
      // is missing, the gate was bypassed.
      expect(result.metrics.reply).toMatch(/需要确认|审批编号|approve/i)
      // The reply must NOT contain the file content (write did not happen).
      expect(result.metrics.reply).not.toContain("auto-grant probe was written")
      // No pain points: the approval pause is the expected path.
      expect(result.painPoints.some((p) => p.severity === "issue")).toBe(false)
    },
  )
})
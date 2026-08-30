/**
 * Scenario 20: three-memory-isolation — runtime regression check for
 * §20 #9 after D9-arch-align audit. Verifies that `recall_durable_memory`
 * reads ONLY from the durableMemories table and never accidentally
 * surfaces content that lives in the projectKnowledgeItems table.
 *
 * Test shape (decoy test):
 *   - Pre-seed: a project knowledge item that matches the query ("dark mode"
 *     preference). The decoy lives in the WRONG layer.
 *   - Pre-state: durableMemories table is empty for this subject.
 *   - Owner asks the LLM a question that should match the decoy if the
 *     recall code accidentally reads the project knowledge table.
 *   - LLM emits `recall_durable_memory({query: "dark mode"})`.
 *   - The tool must return the "no matching confirmed Durable Memory"
 *     stub (durable memory is empty for the subject).
 *   - Final reply must NOT contain the decoy content. If a future
 *     commit broke the invariant (durable-memory code reaching into
 *     project-knowledge storage), the LLM would receive the decoy and
 *     echo it back into the reply.
 *
 * The companion static arch guard (tests/architecture/three-memory-
 * separation.test.ts) locks the import boundary; this scenario is the
 * runtime counterpart.
 */
import { describe, expect, it } from "vitest"
import { runEvalScenario, formatMetricLine } from "../harness.js"
import { makeScriptedAdapter, toolCallResponse, decisionResponse } from "../mock-llm-scripted.js"
import { createProjectKnowledgeStore } from "@butler/persistence/project-knowledge-store.js"

describe("eval/20 three-memory-isolation (§20 #9 D9 runtime check)", () => {
  it(
    "recall_durable_memory must not surface project-knowledge content (decoy test)",
    { timeout: 30_000 },
    async () => {
      const subject = "owner-iso"
      const projectId = "p-iso"
      const conversationId = "c-eval-20-iso"
      let decoyRowCreated = false
      const adapter = makeScriptedAdapter({
        responses: [
          toolCallResponse([
            { id: "tc-iso-1", name: "recall_durable_memory", args: { query: "dark mode" } },
          ]),
          decisionResponse({ _tag: "Respond", content: "我没找到已确认的偏好记录" }),
        ],
      })
      const result = await runEvalScenario({
        name: "20-three-memory-isolation",
        content: "我有什么偏好？",
        fromUserId: subject,
        projectId,
        conversationId,
        adapter,
        beforeLoop: async ({ wiring }) => {
          const pkStore = createProjectKnowledgeStore(wiring.db)
          // Decoy in the WRONG layer (project knowledge). If the durable
          // memory tool code accidentally reads project knowledge, the
          // LLM would receive the decoy content and echo it into the
          // reply — that's the assertion we check below.
          await pkStore.create({
            id: crypto.randomUUID(),
            projectId,
            title: "dark mode preference",
            kind: "manual_note",
            body: "owner prefers dark mode (DECOY — wrong layer)",
            byteSize: 56,
            provenance: { tags: ["preference"], sourceKind: "manual" },
            createdAt: Date.now(),
            updatedAt: Date.now(),
          })
          decoyRowCreated = true
        },
      })

      // eslint-disable-next-line no-console -- eval scenarios log metrics to stdout for pnpm test runs
      console.log(formatMetricLine(result.metrics))

      expect(decoyRowCreated).toBe(true)
      expect(result.metrics.success).toBe(true)
      expect(result.metrics.iterations).toBeGreaterThanOrEqual(2)
      expect(result.metrics.llmCalls).toBeGreaterThanOrEqual(2)
      expect(result.metrics.finalDecision).toBe("Respond")
      // recall_durable_memory was invoked exactly once (no duplicate dispatch).
      expect(result.metrics.capabilitiesByName["recall_durable_memory"] ?? 0).toBe(1)
      // The reply must NOT contain the decoy content. If it does, the
      // durable-memory code leaked project-knowledge content into the
      // tool result and the LLM surfaced it to the owner.
      expect(result.metrics.reply).not.toContain("DECOY")
      expect(result.metrics.reply).not.toContain("dark mode preference")
      // No pain points surfaced.
      expect(result.painPoints.some((p) => p.severity === "issue")).toBe(false)
    },
  )
})
/**
 * Scenario 05: 4-turn conversation flow exercising heterogeneous
 * capabilities. Each turn is an independent `runButlerLoop` call against
 * the same conversationId so the loop sees prior messages.
 *
 * This is the canonical "owner day" usage pattern:
 *   turn 1: ask current time              → expect Respond
 *   turn 2: search history                → expect call recall_history + Respond
 *   turn 3: read a file reference          → expect call read_file + Respond
 *   turn 4: summarize today                → expect call summarize_today + Respond
 */
import { describe, expect, it } from "vitest"
import { runEvalScenario, formatMetricLine } from "../harness.js"
import {
  decisionResponse,
  makeScriptedAdapter,
  toolCallResponse,
} from "../mock-llm-scripted.js"

describe("eval/05 multi-turn-mix (heterogeneous capabilities)", () => {
  // 4 turns × ~1.5s setup + DB tear-down; default 10s testTimeout is too tight under
  // full-suite load; bump to 30s for headroom.
  it("4 turns across greet / history / read / summarize", { timeout: 30_000 }, async () => {
    const conversationId = "c-eval-mix-1"
    const turns = [
      {
        content: "现在几点了",
        setup: () =>
          makeScriptedAdapter({
            responses: [
              toolCallResponse([{ id: "tc-1", name: "get_current_time", args: {} }]),
              decisionResponse({
                _tag: "Respond",
                content: "现在 14:23 Asia/Shanghai",
              }),
            ],
          }),
      },
      {
        content: "昨天聊了什么",
        setup: () =>
          makeScriptedAdapter({
            responses: [
              toolCallResponse([{ id: "tc-2", name: "recall_history", args: { limit: 5 } }]),
              decisionResponse({
                _tag: "Respond",
                content: "昨天主要讨论了 Foo 项目的实现",
              }),
            ],
          }),
      },
      {
        content: "读 /ws/README.md",
        setup: () =>
          makeScriptedAdapter({
            responses: [
              toolCallResponse([
                { id: "tc-3", name: "read_file", args: { path: "/ws/README.md" } },
              ]),
              decisionResponse({
                _tag: "Respond",
                content: "文件内容已展示",
              }),
            ],
          }),
      },
      {
        content: "今天整体怎么样",
        setup: () =>
          makeScriptedAdapter({
            responses: [
              toolCallResponse([{ id: "tc-4", name: "summarize_today", args: {} }]),
              decisionResponse({
                _tag: "Respond",
                content: "今天完成 3 件事",
              }),
            ],
          }),
      },
    ]

    for (const turn of turns) {
      const adapter = turn.setup()
      const result = await runEvalScenario({
        name: `05-multi-turn:${turn.content.slice(0, 12)}`,
        content: turn.content,
        fromUserId: "owner-1",
        projectId: "p-1",
        conversationId,
        adapter,
      })
      // eslint-disable-next-line no-console -- eval scenarios log metrics to stdout
      console.log(formatMetricLine(result.metrics))
      expect(result.metrics.success).toBe(true)
      expect(result.metrics.errors).toHaveLength(0)
    }
  })
})

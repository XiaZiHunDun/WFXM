import { describe, expect, it, vi } from "vitest"
import { AgentKernel } from "../agent-kernel.js"
import type { EventBridge } from "@butler/persistence/event-bridge.js"
import { runConversationLoop } from "./conversation-loop.js"
import type { ToolDefinition } from "../tool-runtime.js"

function makeKernel(): AgentKernel {
  const bridge = {
    appendConversationEvent: vi.fn(async () => undefined),
  } as unknown as EventBridge
  return new AgentKernel({
    bridge,
    conversationId: "c-a7",
    projectId: "test",
    actor: { kind: "agent", id: "test" },
  })
}

describe("runConversationLoop", () => {
  it("returns Respond from plain-text LLM output", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "hi" } })
    const result = await runConversationLoop({
      kernel,
      messages: [
        { role: "system", content: "sys" },
        { role: "user", content: "hi" },
      ],
      llmTools: [],
      ports: {
        complete: async () => ({
          ok: true,
          response: { content: "你好", toolCalls: [] },
        }),
        findTool: () => undefined,
        executeTool: async () => ({ ok: false, reason: "unused" }),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(result.finalDecision).toBe("Respond")
    expect(result.reply).toBe("你好")
    expect(result.iterations).toBe(1)
  })

  it("runs a native tool_call then Responds", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "time?" } })
    const tool: ToolDefinition = {
      name: "get_current_time" as ToolDefinition["name"],
      risk: "low",
      run: async () => ({ ok: true, output: "12:00" }),
    }
    let turn = 0
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "time?" }],
      llmTools: [{ name: "get_current_time" }],
      ports: {
        complete: async () => {
          turn += 1
          if (turn === 1) {
            return {
              ok: true,
              response: {
                content: "",
                toolCalls: [{ id: "tc1", name: "get_current_time", args: {} }],
              },
            }
          }
          return { ok: true, response: { content: "现在是 12:00", toolCalls: [] } }
        },
        findTool: (name) => (name === "get_current_time" ? tool : undefined),
        executeTool: async (def, args) => def.run({ ...args }),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(result.finalDecision).toBe("Respond")
    expect(result.toolCalls).toBe(1)
    expect(result.reply).toBe("现在是 12:00")
    expect(result.traces.some((t) => t.startsWith("get_current_time@"))).toBe(true)
  })

  it("falls back to stub when LLM fails", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "x" } })
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "x" }],
      llmTools: [],
      ports: {
        complete: async () => ({ ok: false, reason: "boom" }),
        findTool: () => undefined,
        executeTool: async () => ({ ok: false, reason: "unused" }),
        stubReply: () => "stub-fallback",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(result.reply).toBe("stub-fallback")
    expect(result.finalDecision).toBe("Finish")
    expect(result.traces.some((t) => t.includes("llm failure"))).toBe(true)
  })
})

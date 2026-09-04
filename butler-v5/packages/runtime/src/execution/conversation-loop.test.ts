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

  it("echoes a WaitForApproval decision and asks for confirmation", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "?" } })
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "?" }],
      llmTools: [],
      ports: {
        complete: async () => ({
          ok: true,
          response: {
            content: JSON.stringify({ _tag: "WaitForApproval", question: "delete the file?" }),
            toolCalls: [],
          },
        }),
        findTool: () => undefined,
        executeTool: async () => ({ ok: false, reason: "unused" }),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(result.finalDecision).toBe("WaitForApproval")
    expect(result.reply).toBe("[需要确认] delete the file?")
    expect(kernel.state).toBe("waiting_approval")
  })

  it("completes on a Finish decision", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "done" } })
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "done" }],
      llmTools: [],
      ports: {
        complete: async () => ({
          ok: true,
          response: {
            content: JSON.stringify({ _tag: "Finish", reason: "all done" }),
            toolCalls: [],
          },
        }),
        findTool: () => undefined,
        executeTool: async () => ({ ok: false, reason: "unused" }),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(result.finalDecision).toBe("Finish")
    expect(result.reply).toBe("stub")
  })

  it("executes a CallCapability decision then Responds", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "read" } })
    const tool: ToolDefinition = {
      name: "read_file" as ToolDefinition["name"],
      risk: "low",
      run: async () => ({ ok: true, output: "file body" }),
    }
    let turn = 0
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "read" }],
      llmTools: [],
      ports: {
        complete: async () => {
          turn += 1
          if (turn === 1) {
            return {
              ok: true,
              response: {
                content: JSON.stringify({
                  _tag: "CallCapability",
                  name: "read_file",
                  arguments: { path: "/a" },
                }),
                toolCalls: [],
              },
            }
          }
          return { ok: true, response: { content: "read it", toolCalls: [] } }
        },
        findTool: (name) => (name === "read_file" ? tool : undefined),
        executeTool: async (def, args) => def.run({ ...args }),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(result.finalDecision).toBe("Respond")
    expect(result.toolCalls).toBe(1)
    expect(result.traces.some((t) => t.startsWith("read_file@"))).toBe(true)
  })

  it("treats an unknown CallCapability tool as Finish", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "x" } })
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "x" }],
      llmTools: [],
      ports: {
        complete: async () => ({
          ok: true,
          response: {
            content: JSON.stringify({ _tag: "CallCapability", name: "nope", arguments: {} }),
            toolCalls: [],
          },
        }),
        findTool: () => undefined,
        executeTool: async () => ({ ok: false, reason: "unused" }),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(result.finalDecision).toBe("CallCapability")
    expect(result.reply).toBe("stub")
    expect(result.traces.some((t) => t.includes("unknown tool: nope"))).toBe(true)
  })

  it("falls back to Finish when delegate_to_subagent is not registered", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "go" } })
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "go" }],
      llmTools: [],
      ports: {
        complete: async () => ({
          ok: true,
          response: {
            content: JSON.stringify({
              _tag: "StartChildRun",
              role: "subagent",
              objective: "summarize",
            }),
            toolCalls: [],
          },
        }),
        findTool: () => undefined,
        executeTool: async () => ({ ok: false, reason: "unused" }),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(result.finalDecision).toBe("StartChildRun")
    expect(result.reply).toBe("stub")
    expect(result.traces.some((t) => t.includes("delegate_to_subagent missing"))).toBe(true)
  })

  it("pushes an error result for an unknown native tool_call and continues", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "hi" } })
    let turn = 0
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "hi" }],
      llmTools: [],
      ports: {
        complete: async () => {
          turn += 1
          if (turn === 1) {
            return {
              ok: true,
              response: {
                content: "",
                toolCalls: [{ id: "tc-ghost", name: "ghost", args: {} }],
              },
            }
          }
          return { ok: true, response: { content: "still alive", toolCalls: [] } }
        },
        findTool: () => undefined,
        executeTool: async () => ({ ok: false, reason: "unused" }),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(result.finalDecision).toBe("Respond")
    expect(result.reply).toBe("still alive")
    expect(result.traces.some((t) => t.includes("unknown tool: ghost"))).toBe(true)
  })

  it("aborts on a stuck loop (same tool+args signature threshold)", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "tick" } })
    const tool: ToolDefinition = {
      name: "tick" as ToolDefinition["name"],
      risk: "low",
      run: async () => ({ ok: true, output: "tick" }),
    }
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "tick" }],
      llmTools: [{ name: "tick" }],
      ports: {
        complete: async () => ({
          ok: true,
          response: {
            content: "",
            toolCalls: [{ id: "tc1", name: "tick", args: { x: 1 } }],
          },
        }),
        findTool: (name) => (name === "tick" ? tool : undefined),
        executeTool: async (def, args) => def.run({ ...args }),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(result.finalDecision).toBe("Finish")
    expect(result.toolCalls).toBe(2)
    expect(result.traces.some((t) => t.includes("stuck-loop"))).toBe(true)
  })

  it("returns clarification reply when the loop is exhausted", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "loop" } })
    const tool: ToolDefinition = {
      name: "tick" as ToolDefinition["name"],
      risk: "low",
      run: async () => ({ ok: true, output: "tick" }),
    }
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "loop" }],
      llmTools: [{ name: "tick" }],
      maxIterations: 1,
      ports: {
        complete: async () => ({
          ok: true,
          response: {
            content: "",
            toolCalls: [{ id: "tc1", name: "tick", args: {} }],
          },
        }),
        findTool: (name) => (name === "tick" ? tool : undefined),
        executeTool: async (def, args) => def.run({ ...args }),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(result.reply).not.toBe("stub")
    expect(result.reply).toMatch(/需要澄清|loop exhausted|未在.*轮内收敛/)
    expect(result.iterations).toBe(1)
    expect(result.finalDecision).toBe("Finish")
    expect(result.traces.some((t) => t.includes("loop exhausted"))).toBe(true)
  })

  it("retries a structured decode failure then Responds", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "x" } })
    let turn = 0
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "x" }],
      llmTools: [],
      ports: {
        complete: async () => {
          turn += 1
          if (turn === 1) {
            return {
              ok: true,
              response: {
                content: JSON.stringify({ _tag: "Bogus", x: 1 }),
                toolCalls: [],
              },
            }
          }
          return { ok: true, response: { content: "recovered", toolCalls: [] } }
        },
        findTool: () => undefined,
        executeTool: async () => ({ ok: false, reason: "unused" }),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(result.finalDecision).toBe("Respond")
    expect(result.reply).toBe("recovered")
    expect(result.traces.some((t) => t.includes("decode failed retry"))).toBe(true)
  })

  it("responds with raw text when the LLM returns malformed JSON", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "x" } })
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "x" }],
      llmTools: [],
      ports: {
        complete: async () => ({
          ok: true,
          response: { content: "{ not json", toolCalls: [] },
        }),
        findTool: () => undefined,
        executeTool: async () => ({ ok: false, reason: "unused" }),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(result.finalDecision).toBe("Respond")
    expect(result.reply).toBe("{ not json")
    expect(result.traces.some((t) => t.includes("decode failed"))).toBe(true)
  })

  it("returns explicit clarification reply when loop exhausts", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "?" } })
    // LLM always emits a new tool call (different args) so the loop never converges.
    let callIndex = 0
    const tool: ToolDefinition = {
      name: "noop" as ToolDefinition["name"],
      description: "",
      inputSchema: { type: "object" },
      execute: async () => ({ ok: true, output: { ok: true } }),
    }
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "?" }],
      llmTools: [tool],
      maxIterations: 3,
      ports: {
        complete: async () => {
          callIndex++
          return {
            ok: true,
            response: {
              content: "",
              toolCalls: [
                {
                  id: `tc-${callIndex}`,
                  name: "noop",
                  args: { i: callIndex },
                },
              ],
            },
          }
        },
        findTool: () => tool,
        executeTool: async () => ({ ok: true, output: { ok: true } }),
        stubReply: () => "stub-fallback",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(result.finalDecision).toBe("Finish")
    expect(result.reply).not.toBe("stub-fallback")
    expect(result.reply).toMatch(/需要澄清|loop exhausted|未在.*轮内收敛|补充信息/i)
    expect(result.traces.some((t) => t.startsWith("loop exhausted"))).toBe(true)
  })
})

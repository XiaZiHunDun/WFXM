import { describe, expect, it, vi } from "vitest"
import type { EventBridge } from "@butler/persistence/event-bridge.js"
import { AgentKernel } from "../agent-kernel.js"
import { RunPauseForApproval } from "../run-engine.js"
import type { ToolDefinition } from "../tool-runtime.js"
import type { ConversationLoopLlmTool, ConversationLoopPorts } from "./conversation-loop.js"
import { runPiConversationLoop } from "./pi-engine.js"

function makeKernel(): AgentKernel {
  const bridge = {
    appendConversationEvent: vi.fn(async () => undefined),
  } as unknown as EventBridge
  return new AgentKernel({
    bridge,
    conversationId: "c-pi",
    projectId: "test",
    actor: { kind: "agent", id: "test" },
  })
}

const tickTool: ToolDefinition = {
  name: "tick" as ToolDefinition["name"],
  risk: "low",
  run: async () => ({ ok: true, output: "tick" }),
}

const tickLlmTool: ConversationLoopLlmTool = {
  name: "tick",
  description: "tick once",
  parameters: { type: "object", properties: {}, required: [] },
}

function makePorts(
  complete: ConversationLoopPorts["complete"],
  overrides: Partial<ConversationLoopPorts> = {},
): ConversationLoopPorts {
  return {
    complete,
    findTool: (name) => (name === "tick" ? tickTool : undefined),
    executeTool: async (def, args) => def.run({ ...args }),
    stubReply: () => "stub",
    logger: { warn: () => undefined, error: () => undefined },
    ...overrides,
  }
}

async function openKernel(): Promise<AgentKernel> {
  const kernel = makeKernel()
  await kernel.openTurn({ userMessage: { role: "user", content: "go" } })
  return kernel
}

describe("runPiConversationLoop", () => {
  it("responds from a JSON decision", async () => {
    const kernel = await openKernel()
    const result = await runPiConversationLoop({
      kernel,
      messages: [
        { role: "system", content: "sys" },
        { role: "user", content: "hi" },
      ],
      llmTools: [],
      ports: makePorts(async () => ({
        ok: true,
        response: {
          content: JSON.stringify({ _tag: "Respond", content: "你好" }),
          toolCalls: [],
        },
      })),
    })

    expect(result.finalDecision).toBe("Respond")
    expect(result.reply).toBe("你好")
    expect(result.iterations).toBe(1)
  })

  it("executes a CallCapability decision and continues", async () => {
    const kernel = await openKernel()
    let calls = 0
    const result = await runPiConversationLoop({
      kernel,
      messages: [{ role: "user", content: "go" }],
      llmTools: [tickLlmTool],
      ports: makePorts(async () => {
        calls += 1
        return calls === 1
          ? {
              ok: true,
              response: {
                content: JSON.stringify({
                  _tag: "CallCapability",
                  name: "tick",
                  arguments: { n: 1 },
                  callId: "tc1",
                }),
                toolCalls: [],
              },
            }
          : {
              ok: true,
              response: {
                content: JSON.stringify({ _tag: "Respond", content: "完成" }),
                toolCalls: [],
              },
            }
      }),
    })

    expect(result.finalDecision).toBe("Respond")
    expect(result.reply).toBe("完成")
    expect(result.toolCalls).toBe(1)
    expect(result.iterations).toBe(2)
  })

  it("executes native tool calls through the bridged AgentTool", async () => {
    const kernel = await openKernel()
    let calls = 0
    const result = await runPiConversationLoop({
      kernel,
      messages: [{ role: "user", content: "go" }],
      llmTools: [tickLlmTool],
      ports: makePorts(async () => {
        calls += 1
        return calls === 1
          ? {
              ok: true,
              response: {
                content: "",
                toolCalls: [{ id: "tc1", name: "tick", args: { n: 1 } }],
              },
            }
          : {
              ok: true,
              response: {
                content: JSON.stringify({ _tag: "Respond", content: "完成" }),
                toolCalls: [],
              },
            }
      }),
    })

    expect(result.reply).toBe("完成")
    expect(result.toolCalls).toBe(1)
    expect(result.iterations).toBe(2)
  })

  it("propagates RunPauseForApproval from a tool", async () => {
    const kernel = await openKernel()
    const pause = new RunPauseForApproval({
      reply: "需要审批后才能继续。",
      finalDecision: "WaitForApproval",
    })
    await expect(
      runPiConversationLoop({
        kernel,
        messages: [{ role: "user", content: "go" }],
        llmTools: [tickLlmTool],
        ports: makePorts(
          async () => ({
            ok: true,
            response: {
              content: JSON.stringify({
                _tag: "CallCapability",
                name: "tick",
                arguments: {},
              }),
              toolCalls: [],
            },
          }),
          {
            executeTool: async () => {
              throw pause
            },
          },
        ),
      }),
    ).rejects.toBe(pause)
  })

  it("treats a cross-module pause error as an approval pause", async () => {
    const kernel = await openKernel()
    // Simulates a second copy of RunPauseForApproval losing `instanceof`.
    const foreign = new Error("run paused for approval")
    await expect(
      runPiConversationLoop({
        kernel,
        messages: [{ role: "user", content: "go" }],
        llmTools: [tickLlmTool],
        ports: makePorts(
          async () => ({
            ok: true,
            response: {
              content: JSON.stringify({
                _tag: "CallCapability",
                name: "tick",
                arguments: {},
              }),
              toolCalls: [],
            },
          }),
          {
            executeTool: async () => {
              throw foreign
            },
          },
        ),
      }),
    ).rejects.toBe(foreign)
  })

  it("retries once on empty content", async () => {
    const kernel = await openKernel()
    let calls = 0
    const result = await runPiConversationLoop({
      kernel,
      messages: [{ role: "user", content: "hi" }],
      llmTools: [],
      ports: makePorts(async () => {
        calls += 1
        return calls === 1
          ? { ok: true, response: { content: "", toolCalls: [] } }
          : {
              ok: true,
              response: {
                content: JSON.stringify({ _tag: "Respond", content: "补上" }),
                toolCalls: [],
              },
            }
      }),
    })

    expect(result.reply).toBe("补上")
    expect(result.iterations).toBe(2)
    expect(result.traces.some((t) => t.includes("empty content retry"))).toBe(true)
  })

  it("skips tool calls once the budget is exhausted", async () => {
    const kernel = await openKernel()
    let calls = 0
    const executeSpy = vi.fn(async () => ({ ok: true, output: "tick" }))
    const result = await runPiConversationLoop({
      kernel,
      messages: [{ role: "user", content: "go" }],
      llmTools: [tickLlmTool],
      maxToolCalls: 0,
      ports: makePorts(
        async () => {
          calls += 1
          return calls === 1
            ? {
                ok: true,
                response: {
                  content: JSON.stringify({
                    _tag: "CallCapability",
                    name: "tick",
                    arguments: {},
                  }),
                  toolCalls: [],
                },
              }
            : {
                ok: true,
                response: {
                  content: JSON.stringify({ _tag: "Respond", content: "预算用尽" }),
                  toolCalls: [],
                },
              }
        },
        { executeTool: executeSpy },
      ),
    })

    expect(executeSpy).not.toHaveBeenCalled()
    expect(result.toolCalls).toBe(0)
    expect(result.reply).toBe("预算用尽")
  })
})

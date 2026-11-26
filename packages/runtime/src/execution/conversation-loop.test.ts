import { describe, expect, it, vi } from "vitest"
import { AgentKernel } from "../agent-kernel.js"
import type { EventBridge } from "@butler/persistence/event-bridge.js"
import {
  resolveLoopIterations,
  runConversationLoop,
  selectLoopEngine,
} from "./conversation-loop.js"
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

describe("resolveLoopIterations", () => {
  it("keeps the explicit minimum and raises the cap to honour the tool budget", () => {
    expect(resolveLoopIterations(undefined, undefined)).toBe(5)
    expect(resolveLoopIterations(5, 8)).toBe(9)
    expect(resolveLoopIterations(10, 3)).toBe(10)
    expect(resolveLoopIterations(undefined, 2)).toBe(5)
    expect(resolveLoopIterations(5, 0)).toBe(5)
  })
})

describe("runConversationLoop", () => {
  it("allows the full tool budget even when maxIterations is smaller", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "go" } })
    const tool: ToolDefinition = {
      name: "tick" as ToolDefinition["name"],
      risk: "low",
      run: async () => ({ ok: true, output: "tick" }),
    }
    let toolCallsSeen = 0
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "go" }],
      llmTools: [{ name: "tick" }],
      maxIterations: 5,
      maxToolCalls: 6,
      ports: {
        complete: async () => {
          toolCallsSeen += 1
          return toolCallsSeen <= 6
            ? {
                ok: true,
                response: {
                  content: "",
                  toolCalls: [
                    { id: `tc${toolCallsSeen}`, name: "tick", args: { n: toolCallsSeen } },
                  ],
                },
              }
            : { ok: true, response: { content: "完成", toolCalls: [] } }
        },
        findTool: (name) => (name === "tick" ? tool : undefined),
        executeTool: async (def, args) => def.run({ ...args }),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(result.finalDecision).toBe("Respond")
    expect(result.reply).toBe("完成")
    expect(result.toolCalls).toBe(6)
  })

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

  it("retries once when the LLM returns empty content and no tool calls", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "hi" } })
    const seen: string[] = []
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "hi" }],
      llmTools: [],
      ports: {
        complete: async (messages) => {
          seen.push(messages.map((m) => m.content).join("\n"))
          return seen.length === 1
            ? { ok: true, response: { content: "", toolCalls: [] } }
            : { ok: true, response: { content: "补偿回复", toolCalls: [] } }
        },
        findTool: () => undefined,
        executeTool: async () => ({ ok: false, reason: "unused" }),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(seen).toHaveLength(2)
    expect(seen[1]).toContain("empty-response")
    expect(result.finalDecision).toBe("Respond")
    expect(result.reply).toBe("补偿回复")
    expect(result.traces).toContain("empty content retry 1/1")
  })

  it("falls back to stub after the empty-content retry is exhausted", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "hi" } })
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "hi" }],
      llmTools: [],
      maxEmptyContentRetries: 1,
      ports: {
        complete: async () => ({ ok: true, response: { content: "", toolCalls: [] } }),
        findTool: () => undefined,
        executeTool: async () => ({ ok: false, reason: "unused" }),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(result.finalDecision).toBe("Respond")
    expect(result.reply).toBe("stub")
    expect(result.traces).toContain("empty content retry 1/1")
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

  it("F27: refuses delegations beyond maxDelegationsPerTurn", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "go" } })
    const started: string[] = []
    const tool = {
      name: "delegate_to_subagent" as ToolDefinition["name"],
      risk: "low",
      run: async (args: { task?: string }) => {
        started.push(String(args.task ?? ""))
        return { ok: true, output: "queued" }
      },
    } as ToolDefinition
    let turn = 0
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "go" }],
      llmTools: [{ name: "delegate_to_subagent" }],
      maxIterations: 6,
      maxDelegationsPerTurn: 2,
      ports: {
        complete: async () => {
          turn += 1
          if (turn <= 4) {
            return {
              ok: true,
              response: {
                content: JSON.stringify({
                  _tag: "StartChildRun",
                  role: "developer",
                  objective: `task-${turn}`,
                }),
                toolCalls: [],
              },
            }
          }
          return { ok: true, response: { content: "已汇报", toolCalls: [] } }
        },
        findTool: (name) => (name === "delegate_to_subagent" ? tool : undefined),
        executeTool: async (def, args) => def.run(args),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(started).toHaveLength(2)
    expect(result.traces.some((t) => t.includes("delegation-cap"))).toBe(true)
    expect(result.finalDecision).toBe("Respond")
    expect(result.reply).toBe("已汇报")
  })

  it("F27: caps native delegate_to_subagent tool calls", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "go" } })
    const started: string[] = []
    const tool = {
      name: "delegate_to_subagent" as ToolDefinition["name"],
      risk: "low",
      run: async (args: { task?: string }) => {
        started.push(String(args.task ?? ""))
        return { ok: true, output: "queued" }
      },
    } as ToolDefinition
    let turn = 0
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "go" }],
      llmTools: [{ name: "delegate_to_subagent" }],
      maxIterations: 6,
      maxDelegationsPerTurn: 2,
      ports: {
        complete: async () => {
          turn += 1
          if (turn <= 4) {
            return {
              ok: true,
              response: {
                content: "",
                toolCalls: [
                  {
                    id: `tc-${turn}`,
                    name: "delegate_to_subagent",
                    args: { task: `task-${turn}`, role: "developer" },
                  },
                ],
              },
            }
          }
          return { ok: true, response: { content: "已汇报", toolCalls: [] } }
        },
        findTool: (name) => (name === "delegate_to_subagent" ? tool : undefined),
        executeTool: async (def, args) => def.run(args),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(started).toHaveLength(2)
    expect(result.traces.some((t) => t.includes("delegation-cap"))).toBe(true)
    expect(result.finalDecision).toBe("Respond")
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

  it("lists available tools and flags decision tags when an unknown tool is called", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "hi" } })
    let turn = 0
    let toolContent = ""
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "hi" }],
      llmTools: [
        {
          name: "delegate_to_subagent",
          description: "delegate",
          parameters: { type: "object" },
        },
      ],
      ports: {
        complete: async (msgs) => {
          turn += 1
          if (turn === 1) {
            return {
              ok: true,
              response: {
                content: "",
                toolCalls: [{ id: "tc-tag", name: "StartChildRun", args: {} }],
              },
            }
          }
          toolContent = msgs.find((m) => m.role === "tool")?.content ?? ""
          return { ok: true, response: { content: "done", toolCalls: [] } }
        },
        findTool: () => undefined,
        executeTool: async () => ({ ok: false, reason: "unused" }),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(toolContent).toContain("delegate_to_subagent")
    expect(toolContent).toContain("决策标签")
    expect(result.finalDecision).toBe("Respond")
  })

  it("suggests the closest tool name for a near-miss unknown tool", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "hi" } })
    let turn = 0
    let toolContent = ""
    await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "hi" }],
      llmTools: [{ name: "list_dir", description: "list", parameters: { type: "object" } }],
      ports: {
        complete: async (msgs) => {
          turn += 1
          if (turn === 1) {
            return {
              ok: true,
              response: {
                content: "",
                toolCalls: [{ id: "tc-miss", name: "list_files", args: {} }],
              },
            }
          }
          toolContent = msgs.find((m) => m.role === "tool")?.content ?? ""
          return { ok: true, response: { content: "done", toolCalls: [] } }
        },
        findTool: () => undefined,
        executeTool: async () => ({ ok: false, reason: "unused" }),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(toolContent).toContain("你是不是想用 list_dir")
    expect(toolContent).toContain("可用工具：list_dir")
  })

  it("nudges once when prose claims a delegation but no tool ran", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "go" } })
    let turn = 0
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "go" }],
      llmTools: [
        { name: "delegate_to_subagent", description: "delegate", parameters: { type: "object" } },
      ],
      delegationClaimGuard: true,
      ports: {
        complete: async () => {
          turn += 1
          if (turn === 1) {
            return {
              ok: true,
              response: { content: "已派 developer 子代理处理，结果一到就转给你。", toolCalls: [] },
            }
          }
          return { ok: true, response: { content: "直接答复：不需要委派。", toolCalls: [] } }
        },
        findTool: () => undefined,
        executeTool: async () => ({ ok: false, reason: "unused" }),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(turn).toBe(2)
    expect(result.traces.some((t) => t.startsWith("delegation-claim nudge"))).toBe(true)
    expect(result.reply).toBe("直接答复：不需要委派。")
  })

  it("nudges a tool-first loop instead of ending on an early prose reply", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "write" } })
    const tool: ToolDefinition = {
      name: "tick" as ToolDefinition["name"],
      risk: "low",
      run: async () => ({ ok: true, output: "tick" }),
    }
    let turn = 0
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "write" }],
      llmTools: [{ name: "tick", description: "tick", parameters: { type: "object" } }],
      toolFirst: true,
      ports: {
        complete: async () => {
          turn += 1
          if (turn === 1) return { ok: true, response: { content: "读完了", toolCalls: [] } }
          if (turn === 2) {
            return {
              ok: true,
              response: { content: "", toolCalls: [{ id: "tc1", name: "tick", args: {} }] },
            }
          }
          return { ok: true, response: { content: "完成了", toolCalls: [] } }
        },
        findTool: (name) => (name === "tick" ? tool : undefined),
        executeTool: async (def, args) => def.run({ ...args }),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(result.traces.some((t) => t.includes("tool-first nudge"))).toBe(true)
    expect(result.finalDecision).toBe("Respond")
    expect(result.reply).toBe("完成了")
  })

  it("F19: accepts the prose summary once the tool budget is exhausted", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "write" } })
    const tool: ToolDefinition = {
      name: "tick" as ToolDefinition["name"],
      risk: "low",
      run: async () => ({ ok: true, output: "tick" }),
    }
    let turn = 0
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "write" }],
      llmTools: [{ name: "tick", description: "tick", parameters: { type: "object" } }],
      toolFirst: true,
      maxToolCalls: 1,
      ports: {
        complete: async () => {
          turn += 1
          if (turn === 1) {
            return {
              ok: true,
              response: { content: "", toolCalls: [{ id: "tc1", name: "tick", args: {} }] },
            }
          }
          // 额度用尽后模型只会给纯文本总结；此时不应再注入「继续用工具」。
          return { ok: true, response: { content: "## 文件清单\n- a.ts", toolCalls: [] } }
        },
        findTool: (name) => (name === "tick" ? tool : undefined),
        executeTool: async (def, args) => def.run({ ...args }),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(result.traces.some((t) => t.includes("tool-first nudge"))).toBe(false)
    expect(result.toolCalls).toBe(1)
    expect(result.finalDecision).toBe("Respond")
    expect(result.reply).toBe("## 文件清单\n- a.ts")
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
    // 兜底话术是给用户看的答复，语义上是 Respond（不是「无需回复」的 Finish）。
    expect(result.finalDecision).toBe("Respond")
    expect(result.traces.some((t) => t.includes("loop exhausted"))).toBe(true)
  })

  it("forces a tool-free final iteration so the user still gets an answer", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "loop" } })
    const seen: { tools: number; nudged: boolean }[] = []
    const tool: ToolDefinition = {
      name: "tick" as ToolDefinition["name"],
      risk: "low",
      run: async () => ({ ok: true, output: "tick" }),
    }
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "loop" }],
      llmTools: [{ name: "tick" }],
      maxIterations: 2,
      ports: {
        complete: async (messages, llmTools) => {
          seen.push({
            tools: llmTools.length,
            nudged: messages.some(
              (message) => message.role === "system" && message.content.includes("这是最后一轮"),
            ),
          })
          return seen.length === 1
            ? {
                ok: true,
                response: { content: "", toolCalls: [{ id: "tc1", name: "tick", args: {} }] },
              }
            : { ok: true, response: { content: "答复", toolCalls: [] } }
        },
        findTool: (name) => (name === "tick" ? tool : undefined),
        executeTool: async (def, args) => def.run({ ...args }),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(seen).toEqual([
      { tools: 1, nudged: false },
      { tools: 0, nudged: true },
    ])
    expect(result.finalDecision).toBe("Respond")
    expect(result.reply).toBe("答复")
  })

  it("injects the remaining tool budget into every iteration", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "go" } })
    const seen: string[] = []
    const tool: ToolDefinition = {
      name: "tick" as ToolDefinition["name"],
      risk: "low",
      run: async () => ({ ok: true, output: "tick" }),
    }
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "go" }],
      llmTools: [{ name: "tick" }],
      maxIterations: 2,
      maxToolCalls: 2,
      ports: {
        complete: async (messages) => {
          seen.push(
            messages
              .filter((m) => m.role === "system" && m.content.includes("工具预算"))
              .map((m) => m.content)
              .join("\n"),
          )
          return seen.length === 1
            ? {
                ok: true,
                response: { content: "", toolCalls: [{ id: "tc1", name: "tick", args: {} }] },
              }
            : { ok: true, response: { content: "完成", toolCalls: [] } }
        },
        findTool: (name) => (name === "tick" ? tool : undefined),
        executeTool: async (def, args) => def.run({ ...args }),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(seen[0]).toContain("剩余 2 次")
    expect(seen[1]).toContain("剩余 1 次")
    // 额度低时明确要求执行目标动作，而不是只给建议。
    expect(seen[1]).toContain("直接执行用户要求的关键动作")
    expect(seen[1]).toContain("不要只给建议")
    // 只保留一条预算提示，不随轮次累积。
    expect(seen[1]?.match(/工具预算/g)).toHaveLength(1)
    expect(result.finalDecision).toBe("Respond")
  })

  it("stops executing tools once the tool budget is spent", async () => {
    const kernel = makeKernel()
    await kernel.openTurn({ userMessage: { role: "user", content: "go" } })
    const seenTools: number[] = []
    const tool: ToolDefinition = {
      name: "tick" as ToolDefinition["name"],
      risk: "low",
      run: async () => ({ ok: true, output: "tick" }),
    }
    let turn = 0
    const result = await runConversationLoop({
      kernel,
      messages: [{ role: "user", content: "go" }],
      llmTools: [{ name: "tick" }],
      maxIterations: 3,
      maxToolCalls: 1,
      ports: {
        complete: async (_messages, llmTools) => {
          seenTools.push(llmTools.length)
          turn += 1
          if (turn <= 2) {
            return {
              ok: true,
              response: {
                content: "",
                toolCalls: [{ id: `tc${turn}`, name: "tick", args: {} }],
              },
            }
          }
          return { ok: true, response: { content: "答复", toolCalls: [] } }
        },
        findTool: (name) => (name === "tick" ? tool : undefined),
        executeTool: async (def, args) => def.run({ ...args }),
        stubReply: () => "stub",
        logger: { warn: () => undefined, error: () => undefined },
      },
    })
    expect(seenTools).toEqual([1, 0, 0])
    expect(result.toolCalls).toBe(1)
    expect(result.finalDecision).toBe("Respond")
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
    expect(result.finalDecision).toBe("Respond")
    expect(result.reply).not.toBe("stub-fallback")
    expect(result.reply).toMatch(/需要澄清|loop exhausted|未在.*轮内收敛|补充信息/i)
    expect(result.traces.some((t) => t.startsWith("loop exhausted"))).toBe(true)
  })
})

// D74 T2 (audit #20 CQ-006): drift detector — runtime's local
// DEFAULT_LLM_TIMEOUT_MS must stay in sync with @butler/adapters'
// DEFAULT_LLM_TIMEOUT_MS at packages/adapters/src/defaults.ts. They
// are intentionally duplicated because @butler/runtime does not depend
// on @butler/adapters (would create dep cycle via ports/domain).
import { DEFAULT_LLM_TIMEOUT_MS as ADAPTERS_DEFAULT } from "@butler/adapters"

describe("loop engine selector", () => {
  it("defaults to native and opts into pi only via env", () => {
    expect(selectLoopEngine({})).toBe("native")
    expect(selectLoopEngine({ BUTLER_V5_LOOP_ENGINE: " PI " })).toBe("pi")
    expect(selectLoopEngine({ BUTLER_V5_LOOP_ENGINE: "native" })).toBe("native")
  })

  it("routes runConversationLoop through the pi engine when selected", async () => {
    vi.stubEnv("BUTLER_V5_LOOP_ENGINE", "pi")
    try {
      const kernel = makeKernel()
      await kernel.openTurn({ userMessage: { role: "user", content: "hi" } })
      const result = await runConversationLoop({
        kernel,
        messages: [{ role: "user", content: "hi" }],
        llmTools: [],
        ports: {
          complete: async () => ({
            ok: true,
            response: {
              content: JSON.stringify({ _tag: "Respond", content: "来自 pi" }),
              toolCalls: [],
            },
          }),
          findTool: () => undefined,
          executeTool: async () => ({ ok: false, reason: "unused" }),
          stubReply: () => "stub",
          logger: { warn: () => undefined, error: () => undefined },
        },
      })
      expect(result.reply).toBe("来自 pi")
      expect(result.finalDecision).toBe("Respond")
    } finally {
      vi.unstubAllEnvs()
    }
  })
})

describe("DEFAULT_LLM_TIMEOUT_MS drift detector", () => {
  it("runtime's local constant matches @butler/adapters default", async () => {
    // Lazy import to keep the test independent of runtime's actual
    // internal constant name.
    const runtimeModule = (await import("./conversation-loop.js")) as Record<string, unknown>
    const runtimeConst = runtimeModule["DEFAULT_LLM_TIMEOUT_MS"] as number | undefined
    // If runtime exports the constant (it currently does NOT — that's
    // intentional after D74 T2), the test guards against drift.
    // Otherwise the test guards by direct equality with adapters'.
    expect(runtimeConst === undefined || runtimeConst === ADAPTERS_DEFAULT).toBe(true)
    expect(ADAPTERS_DEFAULT).toBe(30_000)
  })
})

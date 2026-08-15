import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { EventBridge } from "@butler/runtime/bridge.js"
import { runTool } from "@butler/runtime/tool-runtime.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import {
  WEIBUTLER_LLM_TOOLS,
  findTool,
  makeGetCurrentTimeTool,
  makeRecallHistoryTool,
  makeWeibutlerTools,
} from "./tools.js"

describe("weibutler tools", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let bridge: EventBridge
  const conversationId = "c-tools-1"

  beforeEach(async () => {
    db = await makeTestDb()
    bridge = new EventBridge({ db: db.db, workerId: "w-tools" })
  })

  afterEach(async () => {
    await db.close()
  })

  it("WEIBUTLER_LLM_TOOLS exposes 2 provider-agnostic tool descriptors", () => {
    expect(WEIBUTLER_LLM_TOOLS).toHaveLength(2)
    const names = WEIBUTLER_LLM_TOOLS.map((t) => t.name).sort()
    expect(names).toEqual(["get_current_time", "recall_history"])
    for (const t of WEIBUTLER_LLM_TOOLS) {
      expect(t.description.length).toBeGreaterThan(0)
      expect(t.parameters.type).toBe("object")
    }
  })

  it("makeWeibutlerTools returns runtime ToolDefinitions", () => {
    const tools = makeWeibutlerTools({ bridge, conversationId })
    expect(tools).toHaveLength(2)
    expect(tools.map((t) => t.name as string).sort()).toEqual([
      "get_current_time",
      "recall_history",
    ])
    for (const t of tools) {
      expect(t.risk).toBe("low")
      expect(typeof t.run).toBe("function")
    }
  })

  it("findTool returns matching tool by name", () => {
    const tools = makeWeibutlerTools({ bridge, conversationId })
    const t = findTool(tools, "recall_history")
    expect(t).toBeDefined()
    expect(t?.risk).toBe("low")
  })

  it("findTool returns undefined for unknown name", () => {
    const tools = makeWeibutlerTools({ bridge, conversationId })
    expect(findTool(tools, "does_not_exist")).toBeUndefined()
  })

  it("get_current_time returns an ISO string", async () => {
    const tool = makeGetCurrentTimeTool()
    const result = await runTool(tool, {}, { timeoutMs: 1000 })
    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(typeof result.output).toBe("string")
      expect(result.output).toMatch(/^\d{4}-\d{2}-\d{2}T/)
    }
  })

  it("recall_history returns 'no prior events' when stream is empty", async () => {
    const tool = makeRecallHistoryTool({ bridge, conversationId })
    const result = await runTool(tool, {}, { timeoutMs: 1000 })
    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(result.output).toBe("(no prior events)")
    }
  })

  it("recall_history returns recent events from event_store", async () => {
    await bridge.appendConversationEvent({
      streamId: conversationId,
      eventId: "evt-1",
      eventType: "ConversationStarted",
      correlationId: "corr-1",
      actor: { kind: "system", id: "wechat-forward" },
      event: {
        _tag: "ConversationStarted",
        projectId: "p-1",
        content: "hello from user",
      },
    })
    await bridge.appendConversationEvent({
      streamId: conversationId,
      eventId: "evt-2",
      eventType: "AssistantMessageProduced",
      correlationId: "corr-2",
      actor: { kind: "system", id: "wechat-forward" },
      event: { _tag: "AssistantMessageProduced", content: "hi back" },
    })
    const tool = makeRecallHistoryTool({ bridge, conversationId })
    const result = await runTool(tool, {}, { timeoutMs: 1000 })
    expect(result.ok).toBe(true)
    if (result.ok) {
      const output = String(result.output)
      expect(output).toContain("ConversationStarted")
      expect(output).toContain("hello from user")
      expect(output).toContain("AssistantMessageProduced")
      expect(output).toContain("hi back")
    }
  })

  it("recall_history honors the limit arg (capped at 20)", async () => {
    for (let i = 0; i < 5; i++) {
      await bridge.appendConversationEvent({
        streamId: conversationId,
        eventId: `evt-${i}`,
        eventType: "ConversationStarted",
        correlationId: `corr-${i}`,
        actor: { kind: "system", id: "wechat-forward" },
        event: { _tag: "ConversationStarted", projectId: "p-1", content: `msg-${i}` },
      })
    }
    const tool = makeRecallHistoryTool({ bridge, conversationId })
    const result = await runTool(tool, { limit: 2 }, { timeoutMs: 1000 })
    expect(result.ok).toBe(true)
    if (result.ok) {
      const output = String(result.output)
      const lines = output.split("\n").filter((l) => l.length > 0)
      expect(lines.length).toBe(2)
      expect(output).toContain("msg-3")
      expect(output).toContain("msg-4")
      expect(output).not.toContain("msg-0")
    }
  })

  it("recall_history silently returns error envelope on bridge failure", async () => {
    const brokenBridge = {
      loadStream: vi.fn(async () => {
        throw new Error("db-down")
      }),
    } as unknown as EventBridge
    const tool = makeRecallHistoryTool({
      bridge: brokenBridge,
      conversationId,
    })
    const result = await runTool(tool, {}, { timeoutMs: 1000 })
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.reason).toContain("db-down")
    }
  })
})

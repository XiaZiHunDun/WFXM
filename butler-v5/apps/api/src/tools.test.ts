import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { EventBridge } from "@butler/persistence/event-bridge.js"
import { runTool } from "@butler/runtime/tool-runtime.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import { createProjectKnowledgeStore } from "@butler/persistence/project-knowledge-store.js"
import { createProjectKnowledgeRecord } from "@butler/domain/knowledge/project-knowledge.js"
import {
  WEIBUTLER_LLM_TOOLS,
  findTool,
  makeDelegateToSubagentTool,
  makeGetCurrentTimeTool,
  makeGreetWithTimeTool,
  makeRecallDurableMemoryTool,
  makeRecallHistoryTool,
  makeRecallProjectKnowledgeTool,
  makeSummarizeTodayTool,
  makeWeibutlerTools,
} from "./tools.js"
import type { DurableMemoryStore } from "@butler/persistence"

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

  it("WEIBUTLER_LLM_TOOLS exposes 12 provider-agnostic tool descriptors", () => {
    expect(WEIBUTLER_LLM_TOOLS).toHaveLength(12)
    const names = WEIBUTLER_LLM_TOOLS.map((t) => t.name).sort()
    expect(names).toEqual([
      "delegate_to_subagent",
      "get_current_time",
      "greet_with_time",
      "read_file",
      "recall_document",
      "recall_durable_memory",
      "recall_history",
      "recall_project_knowledge",
      "run_command",
      "send_wechat_file",
      "summarize_today",
      "write_file",
    ])
    for (const t of WEIBUTLER_LLM_TOOLS) {
      expect(t.description.length).toBeGreaterThan(0)
      expect(t.parameters.type).toBe("object")
    }
  })

  it("makeWeibutlerTools returns 11 runtime ToolDefinitions by default (no subagent, no MCP)", () => {
    const tools = makeWeibutlerTools({
      bridge,
      conversationId,
      env: {
        ...process.env,
        BUTLER_V5_MCP_ENABLED: "0",
        BUTLER_V5_SUBAGENT_ENABLED: "0",
      },
    })
    expect(tools).toHaveLength(11)
    expect(tools.map((t) => t.name as string).sort()).toEqual([
      "get_current_time",
      "greet_with_time",
      "read_file",
      "recall_document",
      "recall_durable_memory",
      "recall_history",
      "recall_project_knowledge",
      "run_command",
      "send_wechat_file",
      "summarize_today",
      "write_file",
    ])
    for (const t of tools) {
      expect(typeof t.run).toBe("function")
    }
  })

  it("makeWeibutlerTools includes delegate when subagent enabled", () => {
    const tools = makeWeibutlerTools({
      bridge,
      conversationId,
      env: { BUTLER_V5_SUBAGENT_ENABLED: "1" },
    })
    expect(tools).toHaveLength(12)
    const delegate = tools.find((t) => (t.name as string) === "delegate_to_subagent")
    expect(delegate?.risk).toBe("medium")
  })

  it("makeWeibutlerTools appends MCP tools when opt-in enabled", () => {
    const tools = makeWeibutlerTools({
      bridge,
      conversationId,
      env: { BUTLER_V5_MCP_ENABLED: "1", BUTLER_V5_MCP_TOOL_NAMES: "search" },
    })
    expect(tools).toHaveLength(12)
    expect(tools.some((t) => (t.name as string) === "mcp_search")).toBe(true)
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

  it("P3-2: core tools declare their inputSchema from WEIBUTLER_LLM_TOOLS parameters", () => {
    const tools = makeWeibutlerTools({ bridge, conversationId })
    for (const toolName of ["read_file", "write_file", "run_command", "send_wechat_file"]) {
      const def = findTool(tools, toolName)
      expect(def).toBeDefined()
      const llmRow = WEIBUTLER_LLM_TOOLS.find((t) => t.name === toolName)
      expect(def?.declared?.inputSchema).toEqual(llmRow?.parameters)
    }
  })

  it("get_current_time returns Asia/Shanghai formatted time in Chinese", async () => {
    const tool = makeGetCurrentTimeTool()
    const result = await runTool(tool, {}, { timeoutMs: 1000 })
    expect(result.ok).toBe(true)
    if (result.ok) {
      const output = String(result.output)
      expect(output).toContain("Asia/Shanghai")
      expect(output).toContain("UTC+8")
      // Chinese date format: 2026年8月15日
      expect(output).toMatch(/\d{4}年\d{1,2}月\d{1,2}日/)
      // 24-hour time: HH:MM:SS
      expect(output).toMatch(/\d{2}:\d{2}:\d{2}/)
      // Chinese weekday: 星期一 / 星期二 / 星期三 / 星期四 / 星期五 / 星期六 / 星期日
      expect(output).toMatch(/星期[一二三四五六日]/)
    }
  })

  it("get_current_time does NOT return a UTC ISO timestamp", async () => {
    const tool = makeGetCurrentTimeTool()
    const result = await runTool(tool, {}, { timeoutMs: 1000 })
    expect(result.ok).toBe(true)
    if (result.ok) {
      const output = String(result.output)
      // Should not have the bare ISO 8601 UTC format with Z suffix
      expect(output).not.toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.*Z$/)
    }
  })

  it("greet_with_time returns one of the valid Chinese greetings", async () => {
    const tool = makeGreetWithTimeTool()
    const result = await runTool(tool, {}, { timeoutMs: 1000 })
    expect(result.ok).toBe(true)
    if (result.ok) {
      const output = String(result.output)
      expect(["早晨好", "上午好", "中午好", "下午好", "晚上好", "夜深了"]).toContain(output)
    }
  })

  it("summarize_today returns a string (empty when no recent events)", async () => {
    const tool = makeSummarizeTodayTool({ bridge, conversationId })
    const result = await runTool(tool, {}, { timeoutMs: 1000 })
    expect(result.ok).toBe(true)
    if (result.ok) {
      const output = String(result.output)
      expect(output.length).toBeGreaterThan(0)
      expect(output).toContain("没有事件")
    }
  })

  it("summarize_today counts events in the last 24h, broken down by type", async () => {
    await bridge.appendConversationEvent({
      streamId: conversationId,
      eventId: "evt-s1",
      eventType: "ConversationStarted",
      correlationId: "corr-s1",
      actor: { kind: "system", id: "test" },
      event: { _tag: "ConversationStarted", projectId: "p-1", content: "hello" },
    })
    await bridge.appendConversationEvent({
      streamId: conversationId,
      eventId: "evt-s2",
      eventType: "ConversationStarted",
      correlationId: "corr-s2",
      actor: { kind: "system", id: "test" },
      event: { _tag: "ConversationStarted", projectId: "p-1", content: "hi again" },
    })
    await bridge.appendConversationEvent({
      streamId: conversationId,
      eventId: "evt-s3",
      eventType: "AssistantMessageProduced",
      correlationId: "corr-s3",
      actor: { kind: "system", id: "test" },
      event: { _tag: "AssistantMessageProduced", content: "reply" },
    })
    const tool = makeSummarizeTodayTool({ bridge, conversationId })
    const result = await runTool(tool, {}, { timeoutMs: 1000 })
    expect(result.ok).toBe(true)
    if (result.ok) {
      const output = String(result.output)
      expect(output).toContain("ConversationStarted: 2")
      expect(output).toContain("AssistantMessageProduced: 1")
      expect(output).toContain("3")
    }
  })

  it("summarize_today silently returns error envelope on bridge failure", async () => {
    const brokenBridge = {
      loadStream: vi.fn(async () => {
        throw new Error("db-down")
      }),
    } as unknown as EventBridge
    const tool = makeSummarizeTodayTool({
      bridge: brokenBridge,
      conversationId,
    })
    const result = await runTool(tool, {}, { timeoutMs: 1000 })
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.reason).toContain("db-down")
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
      env: { BUTLER_V5_READ_MODEL: "event_store" },
    })
    const result = await runTool(tool, {}, { timeoutMs: 1000 })
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.reason).toContain("db-down")
    }
  })

  it("recall_history prefers 0002 messages when RuntimeStore is wired (hybrid)", async () => {
    const { createRuntimeStore } = await import("@butler/persistence/runtime-store.js")
    const runtimeStore = createRuntimeStore(db.db)
    const createdAt = new Date()
    await runtimeStore.createConversationWithUserMessage({
      conversationId,
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "relational hello" },
      triggerSource: "channel",
      idempotencyKey: "tools-rel-1",
      createdAt,
    })
    await runtimeStore.appendMessage({
      messageId: crypto.randomUUID(),
      conversationId,
      role: "assistant",
      content: { text: "relational reply" },
      triggerSource: "channel",
      idempotencyKey: "tools-rel-2",
      createdAt: new Date(createdAt.getTime() + 1),
    })
    const tool = makeRecallHistoryTool({
      bridge,
      conversationId,
      runtimeStore,
      env: { BUTLER_V5_READ_MODEL: "hybrid" },
    })
    const result = await runTool(tool, {}, { timeoutMs: 1000 })
    expect(result.ok).toBe(true)
    if (result.ok) {
      const output = String(result.output)
      expect(output).toContain("[user] relational hello")
      expect(output).toContain("[assistant] relational reply")
      expect(output).not.toContain("ConversationStarted")
    }
  })

  it("summarize_today counts relational messages by role in the last 24h", async () => {
    const { createRuntimeStore } = await import("@butler/persistence/runtime-store.js")
    const runtimeStore = createRuntimeStore(db.db)
    const createdAt = new Date()
    await runtimeStore.createConversationWithUserMessage({
      conversationId: "c-tools-sum-rel",
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "hi" },
      triggerSource: "channel",
      idempotencyKey: "sum-rel-1",
      createdAt,
    })
    await runtimeStore.appendMessage({
      messageId: crypto.randomUUID(),
      conversationId: "c-tools-sum-rel",
      role: "assistant",
      content: { text: "yo" },
      triggerSource: "channel",
      idempotencyKey: "sum-rel-2",
      createdAt: new Date(createdAt.getTime() + 1),
    })
    const tool = makeSummarizeTodayTool({
      bridge,
      conversationId: "c-tools-sum-rel",
      runtimeStore,
      env: { BUTLER_V5_READ_MODEL: "hybrid" },
    })
    const result = await runTool(tool, {}, { timeoutMs: 1000 })
    expect(result.ok).toBe(true)
    if (result.ok) {
      const output = String(result.output)
      expect(output).toContain("2 条消息")
      expect(output).toContain("user: 1")
      expect(output).toContain("assistant: 1")
    }
  })

  it("delegate_to_subagent writes ChildRunCreated + outbox and returns child id", async () => {
    const tool = makeDelegateToSubagentTool({
      bridge,
      conversationId,
      actor: { kind: "agent", id: "wechat-butler-v5" },
    })
    const result = await runTool(
      tool,
      { task: "find docs", role: "researcher" },
      { timeoutMs: 2000 },
    )
    expect(result.ok).toBe(true)
    if (result.ok) {
      const output = String(result.output)
      expect(output).toContain("researcher")
      expect(output).toContain("已委派")
      expect(output).toMatch(/child conversation: child-c-tools-1-/)
    }
    const events = await bridge.loadStream(conversationId)
    const childEvents = events.filter((e) => e.eventType === "ChildRunCreated")
    expect(childEvents.length).toBe(1)
  })

  it("delegate_to_subagent returns error envelope when task is missing", async () => {
    const tool = makeDelegateToSubagentTool({ bridge, conversationId })
    const result = await runTool(tool, {}, { timeoutMs: 1000 })
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.reason).toBe("task is required")
    }
  })

  it("delegate_to_subagent defaults role to 'general' when missing or blank", async () => {
    const tool = makeDelegateToSubagentTool({ bridge, conversationId })
    const result = await runTool(tool, { task: "do something", role: "  " }, { timeoutMs: 1000 })
    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(String(result.output)).toContain("general")
    }
  })

  it("delegate_to_subagent is exposed in WEIBUTLER_LLM_TOOLS", () => {
    const names = WEIBUTLER_LLM_TOOLS.map((t) => t.name)
    expect(names).toContain("delegate_to_subagent")
  })

  it("delegate_to_subagent silently returns error envelope on bridge failure", async () => {
    const brokenBridge = {
      appendConversationEventWithOutbox: vi.fn(async () => {
        throw new Error("outbox-down")
      }),
    } as unknown as EventBridge
    const tool = makeDelegateToSubagentTool({ bridge: brokenBridge, conversationId })
    const result = await runTool(tool, { task: "x" }, { timeoutMs: 1000 })
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.reason).toContain("outbox-down")
    }
  })

  it("R8.x.9: delegate_to_subagent with invalid capability returns error envelope", async () => {
    const tool = makeDelegateToSubagentTool({ bridge, conversationId })
    const result = await runTool(
      tool,
      { task: "x", capabilities: ["general", "shell_bomb"] },
      { timeoutMs: 1000 },
    )
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.reason).toContain("invalid capability: shell_bomb")
      expect(result.reason).toContain("general")
    }
    // No outbox message should have been written.
    const events = await bridge.loadStream(conversationId)
    expect(events.filter((e) => e.eventType === "ChildRunCreated")).toHaveLength(0)
  })

  it("R8.x.9: delegate_to_subagent without capabilities defaults to general", async () => {
    const tool = makeDelegateToSubagentTool({ bridge, conversationId })
    const result = await runTool(tool, { task: "default cap" }, { timeoutMs: 1000 })
    expect(result.ok).toBe(true)
    if (result.ok) {
      const events = await bridge.loadStream(conversationId)
      const child = events.find((e) => e.eventType === "ChildRunCreated")
      expect(child).toBeDefined()
      const payload = child?.payload as { capabilities?: { tool: string }[] }
      expect(payload?.capabilities?.length).toBe(1)
      expect(payload?.capabilities?.[0]?.tool).toBe("general")
    }
  })

  it("developer role without capabilities gets exec caps (scheme B)", async () => {
    const tool = makeDelegateToSubagentTool({ bridge, conversationId })
    const result = await runTool(
      tool,
      { task: "implement feature", role: "developer" },
      { timeoutMs: 1000 },
    )
    expect(result.ok).toBe(true)
    if (result.ok) {
      const events = await bridge.loadStream(conversationId)
      const child = events.find((e) => e.eventType === "ChildRunCreated")
      const payload = child?.payload as { capabilities?: { tool: string }[] }
      const caps = (payload?.capabilities ?? []).map((c) => c.tool)
      expect(caps).toContain("write_file")
      expect(caps).toContain("run_command")
    }
  })

  it("recall_durable_memory returns 'no matches' when nothing confirmed matches", async () => {
    const store: DurableMemoryStore = {
      create: async (r) => r,
      get: async () => null,
      update: async (r) => r,
      delete: async () => false,
      listBySubject: async () => [],
      deleteBySourceMessageId: async () => 0,
      deleteBySourceDocumentId: async () => 0,
    }
    const tool = makeRecallDurableMemoryTool({
      durableMemoryStore: store,
      memorySubject: "owner",
    })
    const result = await runTool(tool, { query: "时区" }, { timeoutMs: 1000 })
    expect(result.ok).toBe(true)
    if (result.ok) expect(String(result.output)).toContain("无匹配")
  })

  it("recall_durable_memory refuses without a store (fail-closed)", async () => {
    const tool = makeRecallDurableMemoryTool({})
    const result = await runTool(tool, { query: "x" }, { timeoutMs: 1000 })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.reason).toContain("store unavailable")
  })

  it("recall_durable_memory recalls only active confirmed records by substring", async () => {
    const now = Date.now()
    const rec = (
      id: string,
      status: "candidate" | "confirmed" | "rejected",
      content: string,
      opts: { expiresAt?: number | null; updatedAt?: number } = {},
    ) => ({
      id,
      subject: "owner",
      content,
      sourceKind: "message" as const,
      status,
      confidence: 0.9,
      provenance: { messageId: `m-${id}`, note: "" },
      expiresAt: opts.expiresAt ?? null,
      createdAt: 1,
      updatedAt: opts.updatedAt ?? now,
      confirmedAt: status === "confirmed" ? now : null,
    })
    const store: DurableMemoryStore = {
      create: async (r) => r,
      get: async () => null,
      update: async (r) => r,
      delete: async () => false,
      listBySubject: async ({ status }) =>
        [rec("c1", "confirmed", "时区 Asia/Shanghai"), rec("c2", "confirmed", "过期口令 secret", { expiresAt: now - 10 }), rec("can", "candidate", "时区候选项")].filter(
          (r) => (status ? r.status === status : true),
        ),
      deleteBySourceMessageId: async () => 0,
      deleteBySourceDocumentId: async () => 0,
    }
    const tool = makeRecallDurableMemoryTool({
      durableMemoryStore: store,
      memorySubject: "owner",
    })
    const result = await runTool(tool, { query: "时区" }, { timeoutMs: 1000 })
    expect(result.ok).toBe(true)
    if (result.ok) {
      const output = String(result.output)
      expect(output).toContain("时区 Asia/Shanghai") // confirmed + active
      expect(output).not.toContain("候选项") // candidate excluded
      expect(output).not.toContain("过期口令") // expired excluded
    }
  })

  it("recall_project_knowledge recalls the current project by default", async () => {
    const pk = createProjectKnowledgeStore(db.db)
    const a = createProjectKnowledgeRecord({ projectId: "WFXM", title: "MCP", kind: "manual_note", body: "alpha markers", nowMs: 1 })
    if (!a.ok) throw new Error(a.reason)
    await pk.create(a.value)
    const tool = makeRecallProjectKnowledgeTool({
      bridge,
      conversationId,
      projectId: "WFXM",
      projectKnowledgeStore: pk,
    })
    const result = await runTool(tool, { query: "markers" }, { timeoutMs: 1000 })
    expect(result.ok).toBe(true)
    if (result.ok) expect(String(result.output)).toContain("MCP")
  })

  it("recall_project_knowledge allows explicit cross-project recall", async () => {
    const pk = createProjectKnowledgeStore(db.db)
    const a = createProjectKnowledgeRecord({ projectId: "LingWen", title: "Dual", kind: "manual_note", body: "dualmode alpha", nowMs: 1 })
    if (!a.ok) throw new Error(a.reason)
    await pk.create(a.value)
    const tool = makeRecallProjectKnowledgeTool({
      bridge,
      conversationId,
      projectId: "WFXM",
      projectKnowledgeStore: pk,
    })
    const result = await runTool(tool, { projectId: "LingWen", query: "dualmode" }, { timeoutMs: 1000 })
    expect(result.ok).toBe(true)
    if (result.ok) expect(String(result.output)).toContain("Dual")
  })

  it("recall_project_knowledge tags results across multiple projects", async () => {
    const pk = createProjectKnowledgeStore(db.db)
    const a = createProjectKnowledgeRecord({ projectId: "WFXM", title: "A", kind: "manual_note", body: "shared topic", nowMs: 1 })
    const b = createProjectKnowledgeRecord({ projectId: "LingWen", title: "B", kind: "manual_note", body: "shared topic", nowMs: 2 })
    if (!a.ok || !b.ok) throw new Error("setup failed")
    await pk.create(a.value)
    await pk.create(b.value)
    const tool = makeRecallProjectKnowledgeTool({
      bridge,
      conversationId,
      projectId: "WFXM",
      projectKnowledgeStore: pk,
    })
    const result = await runTool(tool, { projects: "WFXM,LingWen", query: "shared" }, { timeoutMs: 1000 })
    expect(result.ok).toBe(true)
    if (result.ok) {
      const out = String(result.output)
      expect(out).toContain("[WFXM]")
      expect(out).toContain("[LingWen]")
    }
  })

  it("recall_project_knowledge supports * for all projects", async () => {
    const pk = createProjectKnowledgeStore(db.db)
    const a = createProjectKnowledgeRecord({ projectId: "WFXM", title: "A", kind: "manual_note", body: "alpha", nowMs: 1 })
    const b = createProjectKnowledgeRecord({ projectId: "LingWen", title: "B", kind: "manual_note", body: "beta", nowMs: 2 })
    if (!a.ok || !b.ok) throw new Error("setup failed")
    await pk.create(a.value)
    await pk.create(b.value)
    const tool = makeRecallProjectKnowledgeTool({
      bridge,
      conversationId,
      projectId: "WFXM",
      projectKnowledgeStore: pk,
    })
    const result = await runTool(tool, { projects: "*", query: "" }, { timeoutMs: 1000 })
    expect(result.ok).toBe(true)
    if (result.ok) {
      const out = String(result.output)
      expect(out).toContain("[WFXM]")
      expect(out).toContain("[LingWen]")
    }
  })

  it("recall_project_knowledge returns no-match copy when nothing hits", async () => {
    const pk = createProjectKnowledgeStore(db.db)
    const tool = makeRecallProjectKnowledgeTool({
      bridge,
      conversationId,
      projectId: "WFXM",
      projectKnowledgeStore: pk,
    })
    const result = await runTool(tool, { query: "no-such-term" }, { timeoutMs: 1000 })
    expect(result.ok).toBe(true)
    if (result.ok) expect(String(result.output)).toBe("（无匹配的项目知识条目）")
  })

  it("recall_project_knowledge errors when no project context is present", async () => {
    const pk = createProjectKnowledgeStore(db.db)
    const tool = makeRecallProjectKnowledgeTool({
      bridge,
      conversationId,
      projectKnowledgeStore: pk,
    })
    const result = await runTool(tool, {}, { timeoutMs: 1000 })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.reason).toContain("projectId is required")
  })
})

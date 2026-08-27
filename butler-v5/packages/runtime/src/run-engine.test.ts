import { describe, expect, it } from "vitest"
import { eq } from "drizzle-orm"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import { buildWechatRunTrigger } from "@butler/domain/runtime.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { runs } from "@butler/persistence/schema.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import { createWaitingApprovalStep } from "./approval-runtime.js"
import { fixedClock } from "@butler/ports/core/clock.js"
import { ActiveMainRunConflict, InvalidRunTriggerError, RunEngine } from "./run-engine.js"

describe("RunEngine", () => {
  it("creates a bounded main Run and builds a working set", async () => {
    const db = await makeTestDb()
    const store: RuntimeStore = createRuntimeStore(db)
    const engine = new RunEngine(store)
    try {
      const result = await engine.executeInbound(
        {
          conversationId: crypto.randomUUID(),
          messageId: crypto.randomUUID(),
          subject: "owner-1",
          content: "hello",
          idempotencyKey: "inbound-1",
        },
        async (ctx) => ctx,
      )

      expect(result.workingSet.messages.at(-1)).toEqual({ role: "user", content: "hello" })
      expect(result.resumed).toBe(false)
      const messages = await store.listMessages(result.conversationId)
      expect(messages).toHaveLength(1)
    } finally {
      await db.close()
    }
  })

  it("P3-1: accepts a valid normalized RunTrigger", async () => {
    const db = await makeTestDb()
    const store: RuntimeStore = createRuntimeStore(db)
    const engine = new RunEngine(store)
    try {
      const trigger = buildWechatRunTrigger({
        userId: "owner-1",
        conversationId: crypto.randomUUID(),
        content: "hi",
        messageId: "msg-p3-1",
      })
      const result = await engine.executeInbound(
        {
          conversationId: "ignore",
          messageId: crypto.randomUUID(),
          subject: "owner-1",
          content: "hi",
          trigger,
        },
        async (ctx) => ctx,
      )
      expect(result.workingSet.messages.at(-1)).toEqual({ role: "user", content: "hi" })
    } finally {
      await db.close()
    }
  })

  it("P3-1: fails closed when an inbound RunTrigger is malformed", async () => {
    const db = await makeTestDb()
    const store: RuntimeStore = createRuntimeStore(db)
    const engine = new RunEngine(store)
    try {
      const trigger = buildWechatRunTrigger({
        userId: "owner-1",
        conversationId: crypto.randomUUID(),
        content: "hi",
        messageId: "msg-p3-1-bad",
      })
      await expect(
        engine.executeInbound(
          {
            conversationId: "ignore",
            messageId: crypto.randomUUID(),
            subject: "owner-1",
            content: "hi",
            trigger: {
              ...trigger,
              idempotencyKey: "",
              source: "channel",
              conversationRef: "",
            },
          },
          async (ctx) => ctx,
        ),
      ).rejects.toBeInstanceOf(InvalidRunTriggerError)
      // No message/run persisted for the malformed trigger (fail-closed).
      const messages = await store.listMessages(crypto.randomUUID())
      expect(messages).toHaveLength(0)
    } finally {
      await db.close()
    }
  })

  it("applies dev working-set budget and filters chat noise", async () => {
    const db = await makeTestDb()
    const store: RuntimeStore = createRuntimeStore(db)
    const engine = new RunEngine(store)
    const conversationId = crypto.randomUUID()
    const createdAt = new Date()
    try {
      await store.createConversationWithUserMessage({
        conversationId,
        messageId: crypto.randomUUID(),
        subject: "owner-1",
        content: { text: "ping" },
        triggerSource: "channel",
        idempotencyKey: "noise-1",
        createdAt,
      })
      await store.appendMessage({
        messageId: crypto.randomUUID(),
        conversationId,
        role: "assistant",
        content: { text: "pong" },
        triggerSource: "channel",
        idempotencyKey: "noise-2",
        createdAt,
      })
      await store.appendMessage({
        messageId: crypto.randomUUID(),
        conversationId,
        role: "user",
        content: { text: "pwd" },
        triggerSource: "channel",
        idempotencyKey: "noise-3",
        createdAt,
      })
      await store.appendMessage({
        messageId: crypto.randomUUID(),
        conversationId,
        role: "assistant",
        content: { text: "/home/ailearn" },
        triggerSource: "channel",
        idempotencyKey: "noise-4",
        createdAt,
      })
      await store.appendMessage({
        messageId: crypto.randomUUID(),
        conversationId,
        role: "user",
        content: { text: "帮我实现模块" },
        triggerSource: "channel",
        idempotencyKey: "dev-1",
        createdAt,
      })

      const trigger = buildWechatRunTrigger({
        userId: "owner-1",
        conversationId,
        content: "继续开发",
        extraPayload: { workingSetMode: "dev" },
      })
      const result = await engine.executeInbound(
        {
          conversationId,
          messageId: crypto.randomUUID(),
          subject: "owner-1",
          content: "继续开发",
          idempotencyKey: "inbound-dev-ws",
          trigger,
        },
        async (ctx) => ctx,
      )

      expect(result.workingSet.compacted).toBe(false)
      expect(result.workingSet.messages.some((m) => m.content === "ping")).toBe(false)
      expect(result.workingSet.messages.some((m) => m.content.includes("帮我实现模块"))).toBe(true)
    } finally {
      await db.close()
    }
  })

  it("persists RunTrigger metadata when trigger is supplied", async () => {
    const db = await makeTestDb()
    const store: RuntimeStore = createRuntimeStore(db)
    const engine = new RunEngine(store)
    const conversationId = crypto.randomUUID()
    const trigger = buildWechatRunTrigger({
      userId: "wx-u1",
      conversationId,
      content: "hello",
      messageId: "msg-1",
    })
    try {
      await engine.executeInbound(
        {
          conversationId,
          messageId: crypto.randomUUID(),
          subject: trigger.subject,
          content: "hello",
          idempotencyKey: "msg-1",
          trigger,
        },
        async (ctx) => ctx,
      )
      const [run] = await db.select().from(runs).where(eq(runs.conversationId, conversationId))
      expect(run?.triggerSource).toBe("channel")
      expect(run?.budget).toMatchObject({
        maxSteps: 5,
        trustLevel: "trusted",
        triggerPayload: { channelId: "wechat", content: "hello" },
        conversationRef: conversationId,
      })
    } finally {
      await db.close()
    }
  })

  it("refuses executeInbound when a waiting_approval main Run already exists", async () => {
    const db = await makeTestDb()
    const store: RuntimeStore = createRuntimeStore(db)
    const engine = new RunEngine(store)
    const conversationId = crypto.randomUUID()
    const createdAt = new Date("2026-08-20T00:00:00Z")
    try {
      await store.createConversationWithUserMessage({
        conversationId,
        messageId: crypto.randomUUID(),
        subject: "owner-1",
        content: { text: "send" },
        triggerSource: "channel",
        idempotencyKey: "wait-msg",
        createdAt,
      })
      const run = await store.createRun({
        id: crypto.randomUUID(),
        conversationId,
        parentRunId: null,
        triggerSource: "channel",
        idempotencyKey: "wait-run",
        subject: "owner-1",
        goal: "reply",
        budget: { maxSteps: 5 },
        deadline: null,
        createdAt,
      })
      await store.transitionRunStatus(run.id, run.version, "running", createdAt)
      await createWaitingApprovalStep(store, {
        runId: run.id,
        conversationId,
        subject: "owner-1",
        capability: "get_current_time",
        resource: conversationId,
        args: {},
        question: "Confirm?",
        expiresAtMs: Date.now() + 60_000,
        digest: "d-wait",
        kind: "read",
        risk: "low",
      })

      await expect(
        engine.executeInbound(
          {
            conversationId,
            messageId: crypto.randomUUID(),
            subject: "owner-1",
            content: "another message",
            idempotencyKey: "competing-inbound",
          },
          async (ctx) => ctx,
        ),
      ).rejects.toBeInstanceOf(ActiveMainRunConflict)
    } finally {
      await db.close()
    }
  })

  it("resumeRun continues the same runId without createRun", async () => {
    const db = await makeTestDb()
    const store: RuntimeStore = createRuntimeStore(db)
    const engine = new RunEngine(store)
    const conversationId = crypto.randomUUID()
    const createdAt = new Date("2026-08-20T00:00:00Z")
    try {
      await store.createConversationWithUserMessage({
        conversationId,
        messageId: crypto.randomUUID(),
        subject: "owner-1",
        content: { text: "send" },
        triggerSource: "channel",
        idempotencyKey: "resume-msg",
        createdAt,
      })
      const run = await store.createRun({
        id: crypto.randomUUID(),
        conversationId,
        parentRunId: null,
        triggerSource: "channel",
        idempotencyKey: "resume-run",
        subject: "owner-1",
        goal: "reply",
        budget: { maxSteps: 5 },
        deadline: null,
        createdAt,
      })
      const running = await store.transitionRunStatus(run.id, run.version, "running", createdAt)

      const ctx = await engine.resumeRun(
        { runId: running.id, conversationId, content: "确认" },
        async (bodyCtx) => bodyCtx,
      )

      expect(ctx.runId).toBe(running.id)
      expect(ctx.resumed).toBe(true)
      const updated = await store.getRun(running.id)
      expect(updated?.status).toBe("succeeded")
      const allRuns = await db.select().from(runs).where(eq(runs.conversationId, conversationId))
      expect(allRuns).toHaveLength(1)
    } finally {
      await db.close()
    }
  })

  it("trusted inbound auto-resumes waiting_external on the same Run", async () => {
    const db = await makeTestDb()
    const store: RuntimeStore = createRuntimeStore(db)
    const engine = new RunEngine(store)
    const conversationId = crypto.randomUUID()
    const createdAt = new Date("2026-08-20T00:00:00Z")
    const { enterWaitingExternal } = await import("./run-lifecycle.js")
    try {
      await store.createConversationWithUserMessage({
        conversationId,
        messageId: crypto.randomUUID(),
        subject: "wx-u1",
        content: { text: "start" },
        triggerSource: "channel",
        idempotencyKey: "ext-msg-1",
        createdAt,
      })
      const run = await store.createRun({
        id: crypto.randomUUID(),
        conversationId,
        parentRunId: null,
        triggerSource: "channel",
        idempotencyKey: "ext-run-1",
        subject: "wx-u1",
        goal: "reply",
        budget: { maxSteps: 5 },
        deadline: null,
        createdAt,
      })
      const running = await store.transitionRunStatus(run.id, run.version, "running", createdAt)
      await enterWaitingExternal(store, {
        runId: running.id,
        conversationId,
        subject: "wx-u1",
        reason: "await webhook",
      })

      const trigger = buildWechatRunTrigger({
        userId: "wx-u1",
        conversationId,
        content: "webhook done",
        messageId: "ext-msg-2",
      })
      expect(trigger.trustLevel).toBe("trusted")

      const ctx = await engine.executeInbound(
        {
          conversationId,
          messageId: crypto.randomUUID(),
          subject: "wx-u1",
          content: "webhook done",
          idempotencyKey: "ext-msg-2",
          trigger,
        },
        async (bodyCtx) => bodyCtx,
      )

      expect(ctx.runId).toBe(running.id)
      expect(ctx.resumed).toBe(true)
      const updated = await store.getRun(running.id)
      expect(updated?.status).toBe("succeeded")
      const allRuns = await db.select().from(runs).where(eq(runs.conversationId, conversationId))
      expect(allRuns).toHaveLength(1)
    } finally {
      await db.close()
    }
  })

  it("untrusted inbound still conflicts on waiting_external", async () => {
    const db = await makeTestDb()
    const store: RuntimeStore = createRuntimeStore(db)
    const engine = new RunEngine(store)
    const conversationId = crypto.randomUUID()
    const createdAt = new Date("2026-08-20T00:00:00Z")
    const { enterWaitingExternal } = await import("./run-lifecycle.js")
    const { buildChannelRunTrigger } = await import("@butler/domain/runtime.js")
    try {
      await store.createConversationWithUserMessage({
        conversationId,
        messageId: crypto.randomUUID(),
        subject: "u1",
        content: { text: "start" },
        triggerSource: "webhook",
        idempotencyKey: "untrust-msg-1",
        createdAt,
      })
      const run = await store.createRun({
        id: crypto.randomUUID(),
        conversationId,
        parentRunId: null,
        triggerSource: "webhook",
        idempotencyKey: "untrust-run-1",
        subject: "u1",
        goal: "reply",
        budget: { maxSteps: 5 },
        deadline: null,
        createdAt,
      })
      const running = await store.transitionRunStatus(run.id, run.version, "running", createdAt)
      await enterWaitingExternal(store, {
        runId: running.id,
        conversationId,
        subject: "u1",
        reason: "await",
      })
      const trigger = buildChannelRunTrigger({
        channelId: "slack",
        fromSubject: "u1",
        conversationId,
        content: "ping",
        messageId: "untrust-msg-2",
      })
      expect(trigger.trustLevel).toBe("untrusted")
      await expect(
        engine.executeInbound(
          {
            conversationId,
            messageId: crypto.randomUUID(),
            subject: "u1",
            content: "ping",
            idempotencyKey: "untrust-msg-2",
            trigger,
          },
          async (ctx) => ctx,
        ),
      ).rejects.toBeInstanceOf(ActiveMainRunConflict)
    } finally {
      await db.close()
    }
  })

  it("uses injected ClockPort for business timestamps", async () => {
    const db = await makeTestDb()
    const store: RuntimeStore = createRuntimeStore(db)
    const t0 = new Date("2026-01-01T00:00:00Z")
    const engine = new RunEngine(store, undefined, fixedClock(t0))
    try {
      const conversationId = crypto.randomUUID()
      const result = await engine.executeInbound(
        {
          conversationId,
          messageId: crypto.randomUUID(),
          subject: "owner-1",
          content: "hello",
          idempotencyKey: "clock-1",
        },
        async (ctx) => ctx,
      )
      const messages = await store.listMessages(conversationId)
      expect(messages).toHaveLength(1)
      expect(new Date(messages[0].createdAt).getTime()).toBe(t0.getTime())
      const run = await store.getRun(result.runId)
      expect(run?.createdAt.getTime()).toBe(t0.getTime())
    } finally {
      await db.close()
    }
  })
})

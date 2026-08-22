import { describe, expect, it } from "vitest"
import { eq } from "drizzle-orm"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import { buildWechatRunTrigger } from "@butler/domain/runtime.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { runs } from "@butler/persistence/schema.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import { createWaitingApprovalStep } from "./approval-runtime.js"
import { ActiveMainRunConflict, RunEngine } from "./run-engine.js"

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
})

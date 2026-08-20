import { describe, expect, it } from "vitest"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import { createRuntimeStore } from "./runtime-store.js"
import { makeTestDb } from "./testing.js"

describe("RuntimeStore repository", () => {
  it("idempotently creates a conversation with its inbound user message", async () => {
    const db = await makeTestDb()
    const store: RuntimeStore = createRuntimeStore(db)
    const input = {
      conversationId: crypto.randomUUID(),
      messageId: crypto.randomUUID(),
      subject: "owner-1",
      content: { text: "hello" },
      triggerSource: "channel" as const,
      idempotencyKey: "wechat-message-1",
      createdAt: new Date("2026-08-20T00:00:00Z"),
    }
    try {
      const first = await store.createConversationWithUserMessage(input)
      const second = await store.createConversationWithUserMessage({
        ...input,
        conversationId: crypto.randomUUID(),
        messageId: crypto.randomUUID(),
      })

      expect(second).toEqual(first)
      expect(await store.listMessages(first.conversationId)).toEqual([
        expect.objectContaining({
          id: first.messageId,
          conversationId: first.conversationId,
          role: "user",
          content: { text: "hello" },
        }),
      ])
    } finally {
      await db.close()
    }
  })

  it("creates and transitions a main Run with optimistic versioning", async () => {
    const db = await makeTestDb()
    const store: RuntimeStore = createRuntimeStore(db)
    const createdAt = new Date("2026-08-20T00:00:00Z")
    try {
      const inbound = await store.createConversationWithUserMessage({
        conversationId: crypto.randomUUID(),
        messageId: crypto.randomUUID(),
        subject: "owner-1",
        content: { text: "hello" },
        triggerSource: "channel",
        idempotencyKey: "wechat-message-2",
        createdAt,
      })
      const run = await store.createRun({
        id: crypto.randomUUID(),
        conversationId: inbound.conversationId,
        parentRunId: null,
        triggerSource: "channel",
        idempotencyKey: "run-2",
        subject: "owner-1",
        goal: "reply",
        budget: { maxSteps: 5 },
        deadline: null,
        createdAt,
      })

      expect(run.status).toBe("queued")
      const running = await store.transitionRunStatus(
        run.id,
        1,
        "running",
        new Date(createdAt.getTime() + 1),
      )
      expect(running).toEqual(expect.objectContaining({ status: "running", version: 2 }))
      await expect(
        store.transitionRunStatus(run.id, 1, "failed", new Date(createdAt.getTime() + 2)),
      ).rejects.toThrow(/version/i)
    } finally {
      await db.close()
    }
  })

  it("creates a Step for a Run", async () => {
    const db = await makeTestDb()
    const store: RuntimeStore = createRuntimeStore(db)
    const createdAt = new Date("2026-08-20T00:00:00Z")
    try {
      const inbound = await store.createConversationWithUserMessage({
        conversationId: crypto.randomUUID(),
        messageId: crypto.randomUUID(),
        subject: "owner-1",
        content: { text: "hello" },
        triggerSource: "api",
        idempotencyKey: "api-message-1",
        createdAt,
      })
      const run = await store.createRun({
        id: crypto.randomUUID(),
        conversationId: inbound.conversationId,
        parentRunId: null,
        triggerSource: "api",
        idempotencyKey: "api-run-1",
        subject: "owner-1",
        goal: "reply",
        budget: { maxSteps: 5 },
        deadline: null,
        createdAt,
      })
      const step = await store.createStep({
        id: crypto.randomUUID(),
        runId: run.id,
        kind: "model",
        status: "running",
        input: { prompt: "hello" },
        createdAt,
      })

      expect(step).toEqual(
        expect.objectContaining({
          runId: run.id,
          kind: "model",
          status: "running",
          input: { prompt: "hello" },
        }),
      )
    } finally {
      await db.close()
    }
  })
})

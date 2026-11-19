// 锚定契约：同一幂等键/重复 messageId 只落一条 message 与一个 run；并发重复投递只有一个生效；不同消息各自产生一条。
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import type { RuntimeStore } from "../../../packages/domain/src/runtime/index.js"
import { createRuntimeStore } from "../../../packages/persistence/src/runtime-store.js"
import { makeTestDb } from "../../../packages/persistence/src/testing.js"
import { messages, runs } from "../../../packages/persistence/src/schema.js"
import {
  ActiveMainRunConflict,
  RunEngine,
  RunPauseForApproval,
} from "../../../packages/runtime/src/run-engine.js"

const CREATED_AT = new Date("2026-10-01T00:00:00.000Z")

describe("inbound idempotency contract", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let store: RuntimeStore

  beforeEach(async () => {
    db = await makeTestDb()
    store = createRuntimeStore(db)
  })

  afterEach(async () => {
    await db.close()
  })

  it("reuses the conversation and message for a repeated inbound idempotency key", async () => {
    const conversationId = crypto.randomUUID()
    const first = await store.createConversationWithUserMessage({
      conversationId,
      messageId: crypto.randomUUID(),
      subject: "owner-contract",
      content: { text: "hello once" },
      triggerSource: "channel",
      idempotencyKey: "inbound-key-1",
      createdAt: CREATED_AT,
    })

    const replay = await store.createConversationWithUserMessage({
      conversationId: crypto.randomUUID(),
      messageId: crypto.randomUUID(),
      subject: "owner-contract",
      content: { text: "hello once" },
      triggerSource: "channel",
      idempotencyKey: "inbound-key-1",
      createdAt: new Date(CREATED_AT.getTime() + 1000),
    })

    expect(replay).toEqual(first)
    const stored = await store.listMessages(first.conversationId)
    expect(stored).toHaveLength(1)
    expect(stored[0]?.id).toBe(first.messageId)
    expect(stored[0]?.content).toEqual({ text: "hello once" })
    const rows = await db.db.select().from(messages)
    expect(rows.filter((row) => row.idempotencyKey === "inbound-key-1")).toHaveLength(1)
  })

  it("returns the existing Run for a repeated run idempotency key", async () => {
    const conversationId = crypto.randomUUID()
    await store.createConversationWithUserMessage({
      conversationId,
      messageId: crypto.randomUUID(),
      subject: "owner-contract",
      content: { text: "seed" },
      triggerSource: "channel",
      idempotencyKey: "run-idem-msg",
      createdAt: CREATED_AT,
    })
    const base = {
      conversationId,
      parentRunId: null,
      triggerSource: "channel" as const,
      idempotencyKey: "run-idem-1",
      subject: "owner-contract",
      goal: "reply",
      budget: { maxSteps: 5 },
      deadline: null,
      createdAt: CREATED_AT,
    }
    const first = await store.createRun({ ...base, id: crypto.randomUUID() })
    const replay = await store.createRun({ ...base, id: crypto.randomUUID() })

    expect(replay.id).toBe(first.id)
    expect(replay.status).toBe(first.status)
    expect(replay.version).toBe(first.version)
    const rows = await db.db.select().from(runs)
    expect(rows.filter((row) => row.idempotencyKey === "run-idem-1")).toHaveLength(1)
  })

  it("appends a message once per idempotency key", async () => {
    const conversationId = crypto.randomUUID()
    const first = await store.createConversationWithUserMessage({
      conversationId,
      messageId: crypto.randomUUID(),
      subject: "owner-contract",
      content: { text: "first" },
      triggerSource: "channel",
      idempotencyKey: "append-seed",
      createdAt: CREATED_AT,
    })
    const appended = await store.appendMessage({
      messageId: crypto.randomUUID(),
      conversationId: first.conversationId,
      role: "assistant",
      content: { text: "reply once" },
      triggerSource: "channel",
      idempotencyKey: "append-key-1",
      createdAt: new Date(CREATED_AT.getTime() + 1000),
    })
    const replay = await store.appendMessage({
      messageId: crypto.randomUUID(),
      conversationId: first.conversationId,
      role: "assistant",
      content: { text: "reply once" },
      triggerSource: "channel",
      idempotencyKey: "append-key-1",
      createdAt: new Date(CREATED_AT.getTime() + 2000),
    })

    expect(replay.id).toBe(appended.id)
    const stored = await store.listMessages(first.conversationId)
    expect(stored).toHaveLength(2)
    expect(stored.filter((message) => message.idempotencyKey === "append-key-1")).toHaveLength(1)
  })

  it("processes only one of two concurrent duplicate inbound calls", async () => {
    const engine = new RunEngine(store)
    const conversationId = crypto.randomUUID()
    const pauseForApproval = async (): Promise<{ readonly paused: true }> => {
      throw new RunPauseForApproval({ paused: true })
    }
    const call = (messageId: string) =>
      engine.executeInbound(
        {
          conversationId,
          messageId,
          subject: "owner-contract",
          content: "duplicate delivery",
          idempotencyKey: "concurrent-key-1",
        },
        pauseForApproval,
      )

    const settled = await Promise.allSettled([call(crypto.randomUUID()), call(crypto.randomUUID())])
    const fulfilled = settled.filter(
      (result): result is PromiseFulfilledResult<{ readonly paused: true }> =>
        result.status === "fulfilled",
    )
    const rejected = settled.filter(
      (result): result is PromiseRejectedResult => result.status === "rejected",
    )

    expect(fulfilled).toHaveLength(1)
    expect(fulfilled[0]?.value).toEqual({ paused: true })
    expect(rejected).toHaveLength(1)
    expect(rejected[0]?.reason).toBeInstanceOf(ActiveMainRunConflict)

    const runRows = await db.db.select().from(runs)
    const messageRows = await db.db.select().from(messages)
    expect(runRows).toHaveLength(1)
    expect(messageRows).toHaveLength(1)
    expect(runRows[0]?.status).toBe("running")
  })

  it("creates a separate run and message for a different message id after completion", async () => {
    const engine = new RunEngine(store)
    const conversationId = crypto.randomUUID()
    const body = async (): Promise<{ readonly ok: true }> => ({ ok: true })

    const first = await engine.executeInbound(
      {
        conversationId,
        messageId: crypto.randomUUID(),
        subject: "owner-contract",
        content: "first message",
        idempotencyKey: "distinct-key-1",
      },
      body,
    )
    const second = await engine.executeInbound(
      {
        conversationId,
        messageId: crypto.randomUUID(),
        subject: "owner-contract",
        content: "second message",
        idempotencyKey: "distinct-key-2",
      },
      body,
    )

    expect(first).toEqual({ ok: true })
    expect(second).toEqual({ ok: true })
    const runRows = await db.db.select().from(runs)
    const messageRows = await db.db.select().from(messages)
    expect(runRows).toHaveLength(2)
    expect(messageRows).toHaveLength(2)
    expect(runRows.every((run) => run.status === "succeeded")).toBe(true)
    expect(new Set(runRows.map((run) => run.runId)).size).toBe(2)
    expect(runRows.map((run) => run.idempotencyKey).sort()).toEqual([
      "distinct-key-1:run",
      "distinct-key-2:run",
    ])
  })
})

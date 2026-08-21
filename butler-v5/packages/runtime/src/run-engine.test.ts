import { describe, expect, it } from "vitest"
import { eq } from "drizzle-orm"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import { buildWechatRunTrigger } from "@butler/domain/runtime.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import { runs } from "@butler/persistence/schema.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import { RunEngine } from "./run-engine.js"

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
})

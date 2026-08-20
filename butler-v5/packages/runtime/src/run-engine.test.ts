import { describe, expect, it } from "vitest"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
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
})

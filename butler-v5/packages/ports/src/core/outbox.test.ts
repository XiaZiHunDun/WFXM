import { describe, expect, it } from "vitest"
import { memoryOutbox } from "./outbox.js"
import type { OutboxPort } from "./outbox.js"

/** Type narrowing helper avoiding `!` non-null assertions (project ESLint disallows them). */
function expectDefined<T>(value: T | null | undefined): T {
  expect(value).toBeDefined()
  return value as T
}

describe("OutboxPort (memory impl)", () => {
  it("enqueue + claim returns pending messages in FIFO order", async () => {
    const o: OutboxPort = memoryOutbox()
    const a = await o.enqueue({
      streamId: "s1",
      aggregateType: "wechat.send",
      payload: { foo: 1 },
    })
    const b = await o.enqueue({
      streamId: "s2",
      aggregateType: "wechat.send",
      payload: { foo: 2 },
    })
    expect(a.messageId).toMatch(/^mem-\d+$/)
    expect(b.messageId).toMatch(/^mem-\d+$/)
    const claimed = await o.claim()
    expect(claimed).toHaveLength(2)
    const first = expectDefined(claimed[0])
    const second = expectDefined(claimed[1])
    expect(first.messageId).toBe(a.messageId)
    expect(second.messageId).toBe(b.messageId)
    expect(first.payload).toEqual({ foo: 1 })
  })

  it("complete removes message from future claims", async () => {
    const o: OutboxPort = memoryOutbox()
    const { messageId } = await o.enqueue({
      streamId: "s1",
      aggregateType: "x",
      payload: {},
    })
    const first = await o.claim()
    expect(first).toHaveLength(1)
    await o.complete(messageId)
    const second = await o.claim()
    expect(second).toHaveLength(0)
  })

  it("fail marks message as failed (not retried)", async () => {
    const o: OutboxPort = memoryOutbox()
    const { messageId } = await o.enqueue({
      streamId: "s1",
      aggregateType: "x",
      payload: {},
    })
    await o.claim()
    await o.fail(messageId, "downstream rejected")
    const second = await o.claim()
    expect(second).toHaveLength(0)
  })

  it("runWorker invokes handler once per message and completes", async () => {
    const o: OutboxPort = memoryOutbox()
    await o.enqueue({ streamId: "s1", aggregateType: "a", payload: { v: 1 } })
    await o.enqueue({ streamId: "s2", aggregateType: "b", payload: { v: 2 } })
    const seen: string[] = []
    const processed = await o.runWorker(async (msg) => {
      seen.push(msg.messageId)
    })
    expect(seen).toHaveLength(2)
    expect(processed).toBe(2)
    const claimed = await o.claim()
    expect(claimed).toHaveLength(0)
  })
})

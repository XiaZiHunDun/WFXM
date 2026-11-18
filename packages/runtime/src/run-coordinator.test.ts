import { describe, expect, it } from "vitest"
import { RunCoordinator } from "./run-coordinator.js"

describe("RunCoordinator", () => {
  it("serializes concurrent runs for the same conversation", async () => {
    const coordinator = new RunCoordinator()
    const order: number[] = []

    await Promise.all([
      coordinator.withConversationLock("c-1", async () => {
        order.push(1)
        await new Promise((r) => setTimeout(r, 30))
        order.push(2)
      }),
      coordinator.withConversationLock("c-1", async () => {
        order.push(3)
      }),
    ])

    expect(order).toEqual([1, 2, 3])
  })

  it("allows parallel runs for different conversations", async () => {
    const coordinator = new RunCoordinator()
    let a = false
    let b = false

    await Promise.all([
      coordinator.withConversationLock("c-a", async () => {
        a = true
        await new Promise((r) => setTimeout(r, 20))
        expect(b).toBe(true)
      }),
      coordinator.withConversationLock("c-b", async () => {
        b = true
        await new Promise((r) => setTimeout(r, 5))
        expect(a).toBe(true)
      }),
    ])
  })
})

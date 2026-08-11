import { describe, it, expect } from "vitest"
import { Effect } from "effect"
import { migrateV4ToV5, migrateConversations, migrateBlackboardCards } from "./v4-to-v5.js"

describe("infrastructure/migration/v4-to-v5", () => {
  it("migrateConversations returns empty", async () => {
    const result = await Effect.runPromise(migrateConversations())
    expect(result).toEqual([])
  })

  it("migrateBlackboardCards returns empty", async () => {
    const result = await Effect.runPromise(migrateBlackboardCards())
    expect(result).toEqual([])
  })

  it("migrateV4ToV5 returns summary", async () => {
    const result = await Effect.runPromise(migrateV4ToV5())
    expect(result.conversations).toBe(0)
    expect(result.cards).toBe(0)
  })
})

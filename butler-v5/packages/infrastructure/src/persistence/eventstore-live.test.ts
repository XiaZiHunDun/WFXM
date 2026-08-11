// infrastructure/persistence/eventstore-live.test.ts
// EventStore Layer 测试（Mock + Live）

import { describe, it, expect } from "vitest"
import { DrizzleEventStoreLive, MockEventStoreLive } from "./eventstore-live.js"

describe("infrastructure/persistence/eventstore-live", () => {
  describe("MockEventStoreLive", () => {
    it("MockEventStoreLive 已定义", () => {
      expect(MockEventStoreLive).toBeDefined()
    })
  })

  describe("DrizzleEventStoreLive", () => {
    it("DrizzleEventStoreLive 已定义", () => {
      expect(DrizzleEventStoreLive).toBeDefined()
    })
  })

  describe("Layer 区分", () => {
    it("MockEventStoreLive 与 DrizzleEventStoreLive 是不同的 Layer", () => {
      expect(MockEventStoreLive).not.toBe(DrizzleEventStoreLive)
    })
  })
})

// infrastructure/layers.test.ts
// Layer 组合测试 — 验证 ProductionLayer 和 TestLayer 正确组合

import { describe, it, expect } from "vitest"
import { ProductionLayer, TestLayer } from "./layers.js"

describe("infrastructure/layers", () => {
  describe("ProductionLayer", () => {
    it("ProductionLayer 已定义且可导出", () => {
      expect(ProductionLayer).toBeDefined()
    })
  })

  describe("TestLayer", () => {
    it("TestLayer 已定义且可导出", () => {
      expect(TestLayer).toBeDefined()
    })
  })

  describe("Layer 区分", () => {
    it("ProductionLayer 与 TestLayer 是不同的 Layer", () => {
      expect(ProductionLayer).not.toBe(TestLayer)
    })
  })
})

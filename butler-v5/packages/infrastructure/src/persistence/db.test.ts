// infrastructure/persistence/db.test.ts
// 数据库连接 Layer 测试

import { describe, it, expect } from "vitest"
import { Db, DbLive, makeTestDb } from "./db.js"

describe("infrastructure/persistence/db", () => {
  describe("Db Tag", () => {
    it("Db Tag 已定义", () => {
      expect(Db).toBeDefined()
    })

    it("DbLive 已定义", () => {
      expect(DbLive).toBeDefined()
    })
  })

  describe("makeTestDb", () => {
    it("makeTestDb 返回 Layer", () => {
      const layer = makeTestDb()
      expect(layer).toBeDefined()
    })
  })
})

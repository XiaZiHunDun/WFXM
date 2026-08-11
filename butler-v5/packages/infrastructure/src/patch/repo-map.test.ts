// infrastructure/patch/repo-map.test.ts
// 文件重要性评分测试 [OPT-14]

import { describe, it, expect } from "vitest"
import type { LoadBearingMark } from "@butler/domain"
import { scoreFileImportance, buildRepoMap, topKImportant } from "./repo-map.js"

const lbMarks: readonly LoadBearingMark[] = [
  {
    path: "packages/domain/src/errors.ts",
    reason: "全局错误 ADT",
    markedBy: "owner",
    ownerApproved: true,
    alternatives: [],
  },
  {
    path: "packages/ports/src/index.ts",
    reason: "Tag 契约",
    markedBy: "owner",
    ownerApproved: true,
    alternatives: [],
  },
]

describe("infrastructure/patch/repo-map", () => {
  describe("scoreFileImportance", () => {
    it("承重代码标记文件得分最高", () => {
      const score = scoreFileImportance("packages/domain/src/errors.ts", lbMarks)
      expect(score).toBeGreaterThanOrEqual(50)
    })

    it("core/domain/ 目录得分更高", () => {
      const coreScore = scoreFileImportance("packages/core/agent_loop/loop.py", [])
      const appScore = scoreFileImportance("packages/application/src/index.ts", [])
      expect(coreScore).toBeGreaterThanOrEqual(appScore)
    })

    it("普通文件得分低于承重代码", () => {
      const normalScore = scoreFileImportance("src/utils/helper.ts", [])
      const lbScore = scoreFileImportance("packages/domain/src/errors.ts", lbMarks)
      expect(lbScore).toBeGreaterThan(normalScore)
    })

    it("得分不超过 100", () => {
      const score = scoreFileImportance("packages/core/domain/errors.ts", lbMarks)
      expect(score).toBeLessThanOrEqual(100)
    })

    it("测试文件有基础分数", () => {
      const score = scoreFileImportance("packages/domain/src/errors.test.ts", [])
      expect(score).toBeGreaterThan(0)
    })
  })

  describe("buildRepoMap", () => {
    it("构建文件到分数的 Map", () => {
      const files = ["a.ts", "b.ts", "c.test.ts"]
      const map = buildRepoMap(files, [])
      expect(map.size).toBe(3)
      expect(map.has("a.ts")).toBe(true)
    })

    it("空文件列表返回空 Map", () => {
      const map = buildRepoMap([], [])
      expect(map.size).toBe(0)
    })
  })

  describe("topKImportant", () => {
    it("返回 Top-K 重要文件", () => {
      const files = [
        "src/utils.ts",
        "packages/core/loop.ts",
        "packages/domain/src/errors.ts",
        "packages/application/src/index.ts",
        "packages/shared/helpers.ts",
      ]
      const top = topKImportant(files, lbMarks, 3)
      expect(top.length).toBe(3)
      // errors.ts 应该是第一（承重代码 + domain/）
      expect(top[0]).toBe("packages/domain/src/errors.ts")
    })

    it("K 超过文件数时返回全部", () => {
      const files = ["a.ts", "b.ts"]
      const top = topKImportant(files, [], 10)
      expect(top.length).toBe(2)
    })
  })
})

// infrastructure/patch/relative-indenter.test.ts
// 多策略 Patch 应用测试 [OPT-13]

import { describe, it, expect } from "vitest"
import { applyPatch } from "./relative-indenter.js"

describe("infrastructure/patch/relative-indenter", () => {
  describe("applyPatch — unified diff", () => {
    it("应用 unified diff 格式的 patch", () => {
      const content = "line1\nline2\nline3"
      const patch = "@@ -1,3 +1,3 @@\n line1\n+line2-modified\n line3"
      const result = applyPatch(content, patch)
      expect(result).toBe("line1\nline2-modified\nline3")
    })

    it("unified diff 删除行", () => {
      const content = "line1\nline2\nline3"
      const patch = "@@ -1,3 +1,2 @@\n line1\n-line2\n line3"
      const result = applyPatch(content, patch)
      expect(result).toBe("line1\nline3")
    })

    it("unified diff 添加行", () => {
      const content = "line1\nline3"
      const patch = "@@ -1,2 +1,3 @@\n line1\n+line2\n line3"
      const result = applyPatch(content, patch)
      expect(result).toContain("line1")
      expect(result).toContain("line2")
    })
  })

  describe("applyPatch — search/replace", () => {
    it("应用 search/replace 格式的 patch", () => {
      const content = "function hello() {\n  return 'world'\n}"
      const patch = "<<<<<<< SEARCH\nreturn 'world'\n=======\nreturn 'hello'\n>>>>>>> REPLACE"
      const result = applyPatch(content, patch)
      expect(result).toContain("return 'hello'")
      expect(result).not.toContain("return 'world'")
    })

    it("search/replace 无匹配时返回原内容", () => {
      const content = "function hello() {\n  return 'world'\n}"
      const patch = "<<<<<<< SEARCH\nnonexistent\n=======\nreplacement\n>>>>>>> REPLACE"
      const result = applyPatch(content, patch)
      expect(result).toBe(content)
    })
  })

  describe("applyPatch — 相对缩进", () => {
    it("对非 diff 格式的 patch 使用相对缩进插入", () => {
      const content = "  const x = 1\n  const y = 2"
      const patch = "const z = 3"
      const result = applyPatch(content, patch)
      // 应检测到缩进为 2 空格，patch 行被缩进后追加
      expect(result).toContain("const z = 3")
    })
  })
})

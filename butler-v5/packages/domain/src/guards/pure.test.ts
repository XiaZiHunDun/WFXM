import { describe, it, expect } from "vitest"
import {
  pickVerificationLevel,
  verifyChain,
  pickHealLayer,
  scoreDeletionRisk,
  verifyEvidence,
  checkRoleSeparation,
} from "./pure.js"

describe("guards/pure", () => {
  describe("pickVerificationLevel", () => {
    it("returns Fast for generated tools with < 50 LOC", () => {
      expect(pickVerificationLevel({ added: 30, removed: 0 }, true)).toBe("Fast")
    })

    it("returns Standard for generated tools with >= 50 LOC", () => {
      expect(pickVerificationLevel({ added: 60, removed: 0 }, true)).toBe("Standard")
    })

    it("returns Standard for non-generated tools", () => {
      expect(pickVerificationLevel({ added: 10, removed: 0 }, false)).toBe("Standard")
    })
  })

  describe("verifyChain", () => {
    it("returns completeness 1 when all expected links present", () => {
      const result = verifyChain(
        { mainFile: "src/App.tsx", expectedLinks: ["src/App.test.tsx", "src/index.ts"] },
        ["src/App.tsx", "src/App.test.tsx", "src/index.ts"],
      )
      expect(result.completeness).toBe(1)
      expect(result.missing).toEqual([])
    })

    it("returns partial completeness when some links missing", () => {
      const result = verifyChain(
        { mainFile: "src/App.tsx", expectedLinks: ["src/App.test.tsx", "src/index.ts"] },
        ["src/App.tsx", "src/App.test.tsx"],
      )
      expect(result.completeness).toBe(0.5)
      expect(result.missing).toEqual(["src/index.ts"])
    })

    it("returns completeness 1 when no expected links", () => {
      const result = verifyChain({ mainFile: "src/readme.md", expectedLinks: [] }, [
        "src/readme.md",
      ])
      expect(result.completeness).toBe(1)
      expect(result.missing).toEqual([])
    })
  })

  describe("pickHealLayer", () => {
    it("returns retry for retryCount < 2 and non-GuardRejected", () => {
      expect(pickHealLayer({ _tag: "LLMUnavailable", provider: "test" }, 0)).toBe("retry")
      expect(pickHealLayer({ _tag: "ToolFailed", toolId: "t1", cause: "x" }, 1)).toBe("retry")
    })

    it("returns fallback for LLMUnavailable/ToolFailed after retries", () => {
      expect(pickHealLayer({ _tag: "LLMUnavailable", provider: "test" }, 2)).toBe("fallback")
      expect(pickHealLayer({ _tag: "ToolFailed", toolId: "t1", cause: "x" }, 3)).toBe("fallback")
    })

    it("returns owner-notify for GuardRejected even at retryCount 0", () => {
      expect(pickHealLayer({ _tag: "GuardRejected", reason: { _tag: "MissingEvidence" } }, 0)).toBe(
        "owner-notify",
      )
    })

    it("returns owner-notify for other errors after retries", () => {
      expect(pickHealLayer({ _tag: "ContextOverflow", tokens: 1000 }, 2)).toBe("owner-notify")
    })
  })

  describe("scoreDeletionRisk", () => {
    it("returns 0 for non-load-bearing files", () => {
      const result = scoreDeletionRisk("src/utils.ts", [], 50)
      expect(result.score).toBe(0)
      expect(result.reasons).toEqual([])
    })

    it("returns 80+ for load-bearing marked files", () => {
      const marks = [
        {
          path: "src/loop.ts",
          reason: "核心循环",
          markedBy: "owner" as const,
          ownerApproved: true,
        },
      ]
      const result = scoreDeletionRisk("src/loop.ts", marks, 50)
      expect(result.score).toBe(80)
      expect(result.reasons).toContain("核心循环")
    })

    it("adds 20 when locRemoved > 100", () => {
      const marks = [
        {
          path: "src/loop.ts",
          reason: "核心循环",
          markedBy: "owner" as const,
          ownerApproved: true,
        },
      ]
      const result = scoreDeletionRisk("src/loop.ts", marks, 150)
      expect(result.score).toBe(100)
    })

    it("caps score at 100", () => {
      const marks = [
        { path: "src/loop.ts", reason: "核心", markedBy: "owner" as const, ownerApproved: true },
        {
          path: "src/loop.ts",
          reason: "关键",
          markedBy: "auto-detected" as const,
          ownerApproved: true,
        },
      ]
      const result = scoreDeletionRisk("src/loop.ts", marks, 200)
      expect(result.score).toBe(100)
    })
  })

  describe("verifyEvidence", () => {
    it("returns fail for empty evidence files", () => {
      const findings = verifyEvidence([], { added: 0, removed: 0 })
      expect(findings).toHaveLength(1)
      expect(findings[0]?.status).toBe("fail")
      expect(findings[0]?.guard).toBe("intent-receipt")
    })

    it("returns pass with file count", () => {
      const findings = verifyEvidence(["a.ts", "b.ts"], { added: 20, removed: 5 })
      expect(findings).toHaveLength(1)
      expect(findings[0]?.status).toBe("pass")
      expect(findings[0]?.detail).toContain("2 files")
      expect(findings[0]?.detail).toContain("+20")
    })
  })

  describe("checkRoleSeparation", () => {
    it("returns ok for different author and reviewer", () => {
      expect(checkRoleSeparation("claude-3-5-sonnet", "claude-3-5-haiku")).toEqual({ ok: true })
    })

    it("returns not ok for same author and reviewer", () => {
      const result = checkRoleSeparation("claude-3-5-sonnet", "claude-3-5-sonnet")
      expect(result.ok).toBe(false)
      expect(result.reason).toContain("cannot review their own work")
    })
  })
})

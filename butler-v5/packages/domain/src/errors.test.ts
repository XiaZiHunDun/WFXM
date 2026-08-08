import { describe, it, expect } from "vitest"
import type { LoopError, GuardReason } from "./errors.js"

describe("domain/errors", () => {
  it("LoopError types are valid", () => {
    const err: LoopError = {
      _tag: "LLMUnavailable",
      provider: "anthropic",
    }
    expect(err._tag).toBe("LLMUnavailable")
    expect(err.provider).toBe("anthropic")
  })

  it("GuardReason sub-types are valid", () => {
    const reason: GuardReason = {
      _tag: "MissingEvidence",
    }
    expect(reason._tag).toBe("MissingEvidence")
  })

  it("GuardRejected wraps a GuardReason", () => {
    const err: LoopError = {
      _tag: "GuardRejected",
      reason: { _tag: "LoadBearingTouched", path: "src/loop.ts" },
    }
    expect(err._tag).toBe("GuardRejected")
    if (err._tag === "GuardRejected") {
      expect(err.reason._tag).toBe("LoadBearingTouched")
    }
  })
})

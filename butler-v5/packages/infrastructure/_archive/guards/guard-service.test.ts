import { describe, it, expect, beforeEach } from "vitest"
import { Effect } from "effect"
import {
  GuardServiceLive,
  simOwnerOffline,
  simOwnerOnline,
  registerLoadBearingMark,
  clearLoadBearingMarks,
  signPayload,
} from "./index.js"
import { GuardService } from "@butler/ports"

describe("infrastructure/guards/GuardServiceLive", () => {
  beforeEach(() => {
    simOwnerOnline()
    clearLoadBearingMarks()
  })

  describe("G-1: issueReceipt", () => {
    it("creates an IntentReceipt with UUID", async () => {
      const program = Effect.gen(function* () {
        const guard = yield* GuardService
        return yield* guard.issueReceipt({
          intent: "Add login button",
          evidenceFiles: ["src/Login.tsx", "src/Login.test.tsx"],
          locDelta: { added: 50, removed: 5 },
          authorAgent: "claude-3-5-sonnet",
        })
      })

      const result = await Effect.runPromise(Effect.provide(program, GuardServiceLive))
      expect(result.id).toMatch(/^[0-9a-f-]{36}$/)
      expect(result.intent).toBe("Add login button")
      expect(result.evidenceFiles).toEqual(["src/Login.tsx", "src/Login.test.tsx"])
      expect(result.authorAgent).toBe("claude-3-5-sonnet")
    })
  })

  describe("G-2: checkLoadBearing", () => {
    it("allows write on non-load-bearing path", async () => {
      const program = Effect.gen(function* () {
        const guard = yield* GuardService
        return yield* guard.checkLoadBearing("src/utils.ts", "write")
      })

      const result = await Effect.runPromise(Effect.provide(program, GuardServiceLive))
      expect(result.allowed).toBe(true)
    })

    it("blocks write on owner-approved load-bearing path", async () => {
      registerLoadBearingMark({
        path: "src/loop.ts",
        reason: "核心循环",
        markedBy: "owner",
        ownerApproved: true,
      })

      const program = Effect.gen(function* () {
        const guard = yield* GuardService
        return yield* guard.checkLoadBearing("src/loop.ts", "write")
      })

      const result = await Effect.runPromise(Effect.provide(program, GuardServiceLive))
      expect(result.allowed).toBe(false)
      expect(result.reason).toContain("核心循环")
    })

    it("blocks delete on load-bearing path", async () => {
      registerLoadBearingMark({
        path: "src/loop.ts",
        reason: "核心循环",
        markedBy: "owner",
        ownerApproved: true,
      })

      const program = Effect.gen(function* () {
        const guard = yield* GuardService
        return yield* guard.checkLoadBearing("src/loop.ts", "delete")
      })

      const result = await Effect.runPromise(Effect.provide(program, GuardServiceLive))
      expect(result.allowed).toBe(false)
      expect(result.reason).toContain("删除")
    })

    it("allows write on not-yet-approved mark", async () => {
      registerLoadBearingMark({
        path: "src/config.ts",
        reason: "全局配置",
        markedBy: "ai-suggested",
        ownerApproved: false,
      })

      const program = Effect.gen(function* () {
        const guard = yield* GuardService
        return yield* guard.checkLoadBearing("src/config.ts", "write")
      })

      const result = await Effect.runPromise(Effect.provide(program, GuardServiceLive))
      expect(result.allowed).toBe(true)
    })
  })

  describe("G-3: checkOwnerOnline", () => {
    it("allows when owner is online", async () => {
      const program = Effect.gen(function* () {
        const guard = yield* GuardService
        return yield* guard.checkOwnerOnline({ toolId: "write_file", category: "write" })
      })

      const result = await Effect.runPromise(Effect.provide(program, GuardServiceLive))
      expect(result.decision).toBe("allow")
    })

    it("denies write actions when owner is offline", async () => {
      simOwnerOffline()
      const program = Effect.gen(function* () {
        const guard = yield* GuardService
        return yield* guard.checkOwnerOnline({ toolId: "write_file", category: "write" })
      })

      const result = await Effect.runPromise(Effect.provide(program, GuardServiceLive))
      expect(result.decision).toBe("deny")
    })
  })

  describe("G-4: verifyHumanSig", () => {
    it("verifies valid signature", async () => {
      const payload = { action: "modify", path: "src/loop.ts" }
      const sig = signPayload(payload)

      const program = Effect.gen(function* () {
        const guard = yield* GuardService
        return yield* guard.verifyHumanSig(sig, payload)
      })

      const result = await Effect.runPromise(Effect.provide(program, GuardServiceLive))
      expect(result).toBe(true)
    })

    it("rejects invalid signature", async () => {
      const payload = { action: "modify", path: "src/loop.ts" }

      const program = Effect.gen(function* () {
        const guard = yield* GuardService
        return yield* guard.verifyHumanSig("invalid-sig", payload)
      })

      const result = await Effect.runPromise(Effect.provide(program, GuardServiceLive))
      expect(result).toBe(false)
    })

    it("rejects tampered payload", async () => {
      const originalPayload = { action: "modify", path: "src/loop.ts" }
      const sig = signPayload(originalPayload)
      const tamperedPayload = { action: "modify", path: "src/core.ts" }

      const program = Effect.gen(function* () {
        const guard = yield* GuardService
        return yield* guard.verifyHumanSig(sig, tamperedPayload)
      })

      const result = await Effect.runPromise(Effect.provide(program, GuardServiceLive))
      expect(result).toBe(false)
    })
  })

  describe("G-5: verifyChain", () => {
    it("returns completeness 1 when all expected links present", async () => {
      const program = Effect.gen(function* () {
        const guard = yield* GuardService
        return yield* guard.verifyChain(
          { mainFile: "src/App.tsx", expectedLinks: ["src/App.test.tsx", "src/index.ts"] },
          ["src/App.tsx", "src/App.test.tsx", "src/index.ts"],
        )
      })

      const result = await Effect.runPromise(Effect.provide(program, GuardServiceLive))
      expect(result.completeness).toBe(1)
      expect(result.missing).toEqual([])
    })

    it("reports missing links", async () => {
      const program = Effect.gen(function* () {
        const guard = yield* GuardService
        return yield* guard.verifyChain(
          { mainFile: "src/App.tsx", expectedLinks: ["src/App.test.tsx", "src/index.ts"] },
          ["src/App.tsx"],
        )
      })

      const result = await Effect.runPromise(Effect.provide(program, GuardServiceLive))
      expect(result.completeness).toBe(0)
      expect(result.missing).toEqual(["src/App.test.tsx", "src/index.ts"])
    })
  })

  describe("G-6: pickVerification", () => {
    it("returns Fast for generated tools with small delta", async () => {
      const program = Effect.gen(function* () {
        const guard = yield* GuardService
        return yield* guard.pickVerification({ added: 30, removed: 0 }, true)
      })

      const result = await Effect.runPromise(Effect.provide(program, GuardServiceLive))
      expect(result).toBe("Fast")
    })

    it("returns Standard for non-generated tools", async () => {
      const program = Effect.gen(function* () {
        const guard = yield* GuardService
        return yield* guard.pickVerification({ added: 10, removed: 0 }, false)
      })

      const result = await Effect.runPromise(Effect.provide(program, GuardServiceLive))
      expect(result).toBe("Standard")
    })
  })

  describe("G-7: checkRoleSeparation", () => {
    it("allows different author and reviewer", async () => {
      const program = Effect.gen(function* () {
        const guard = yield* GuardService
        return yield* guard.checkRoleSeparation("claude-3-5-sonnet", "claude-3-5-haiku")
      })

      const result = await Effect.runPromise(Effect.provide(program, GuardServiceLive))
      expect(result.ok).toBe(true)
    })

    it("rejects same author and reviewer", async () => {
      const program = Effect.gen(function* () {
        const guard = yield* GuardService
        return yield* guard.checkRoleSeparation("claude-3-5-sonnet", "claude-3-5-sonnet")
      })

      const result = await Effect.runPromise(Effect.provide(program, GuardServiceLive))
      expect(result.ok).toBe(false)
    })
  })

  describe("G-8: heal", () => {
    it("retries and succeeds on retryable error", async () => {
      let callCount = 0
      const flakyEffect = Effect.sync(() => {
        callCount++
        if (callCount < 3) {
          return Effect.fail({ _tag: "LLMUnavailable", provider: "test" })
        }
        return Effect.succeed("success")
      }).pipe(Effect.flatten)

      const program = Effect.gen(function* () {
        const guard = yield* GuardService
        return yield* guard.heal(flakyEffect, { maxRetry: 3 })
      })

      const result = await Effect.runPromise(Effect.provide(program, GuardServiceLive))
      expect(result).toBe("success")
      expect(callCount).toBe(3)
    })

    it("uses fallback when retries exhausted", async () => {
      const alwaysFail = Effect.fail({ _tag: "LLMUnavailable", provider: "test" })

      const program = Effect.gen(function* () {
        const guard = yield* GuardService
        return yield* guard.heal(alwaysFail, {
          maxRetry: 2,
          fallback: () => Effect.succeed("fallback-result"),
        })
      })

      const result = await Effect.runPromise(Effect.provide(program, GuardServiceLive))
      expect(result).toBe("fallback-result")
    })

    it("fails with HealFailed when no fallback and retries exhausted", async () => {
      const alwaysFail = Effect.fail({ _tag: "LLMUnavailable", provider: "test" })

      const program = Effect.gen(function* () {
        const guard = yield* GuardService
        return yield* guard.heal(alwaysFail, { maxRetry: 1 })
      })

      await expect(
        Effect.runPromise(Effect.provide(program, GuardServiceLive)),
      ).rejects.toBeDefined()
    })
  })

  describe("G-9: archiveAntiPattern", () => {
    it("archives a pattern without error", async () => {
      const program = Effect.gen(function* () {
        const guard = yield* GuardService
        yield* guard.archiveAntiPattern("fake-completion", { reason: "no evidence files" })
        return true
      })

      const result = await Effect.runPromise(Effect.provide(program, GuardServiceLive))
      expect(result).toBe(true)
    })
  })

  describe("G-10: scheduleChaos", () => {
    it("schedules a chaos scenario", async () => {
      const program = Effect.gen(function* () {
        const guard = yield* GuardService
        yield* guard.scheduleChaos("fake-completion", "0 3 1 * *")
        return true
      })

      const result = await Effect.runPromise(Effect.provide(program, GuardServiceLive))
      expect(result).toBe(true)
    })
  })
})

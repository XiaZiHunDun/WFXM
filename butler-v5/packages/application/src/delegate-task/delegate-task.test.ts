import { describe, it, expect } from "vitest"
import { Effect, Layer } from "effect"
import { delegateTask, MockProjectServiceLive } from "./index.js"
import { GuardService, ProjectService } from "@butler/ports"
import type { ProjectId } from "@butler/domain"

const pid = "proj-1" as unknown as ProjectId

function makeMockGuard() {
  return GuardService.of({
    issueReceipt: () =>
      Effect.succeed({
        id: "r-1",
        intent: "test",
        evidenceFiles: [],
        locDelta: { added: 0, removed: 0 },
        chainCompleteness: 1,
        guardFindings: [],
        authorAgent: "test",
        createdAt: 1,
      }),
    checkLoadBearing: () => Effect.succeed({ allowed: true }),
    checkOwnerOnline: () => Effect.succeed({ decision: "allow" as const, reason: "ok" }),
    verifyHumanSig: () => Effect.succeed(true),
    verifyChain: () => Effect.succeed({ completeness: 1, missing: [] }),
    pickVerification: () => Effect.succeed("Fast" as const),
    checkRoleSeparation: () => Effect.succeed({ ok: true }),
    heal: (effect) => effect,
    archiveAntiPattern: () => Effect.void,
    scheduleChaos: () => Effect.void,
  })
}

describe("application/delegate-task", () => {
  it("returns receipt when evidence exists", async () => {
    const MockGuardLive = Layer.succeed(GuardService, makeMockGuard())

    const program = Effect.provide(
      delegateTask({
        projectId: pid,
        specRef: "spec-1",
      }),
      Layer.mergeAll(MockProjectServiceLive, MockGuardLive),
    )

    const result = await Effect.runPromise(program)
    expect(result.intent).toContain("proj-1")
    expect(result.evidenceFiles).toHaveLength(2)
  })

  it("fails with MissingEvidence when no evidence files", async () => {
    const NoEvidenceProjectLive = Layer.succeed(
      ProjectService,
      ProjectService.of({
        loadSpec: () => Effect.succeed({}),
        delegateTask: () =>
          Effect.succeed({
            id: "r-1",
            intent: "test",
            evidenceFiles: [],
            locDelta: { added: 0, removed: 0 },
            chainCompleteness: 1,
            guardFindings: [],
            authorAgent: "test",
            createdAt: 1,
          }),
      }),
    )

    const MockGuardLive = Layer.succeed(GuardService, makeMockGuard())

    const program = Effect.provide(
      delegateTask({
        projectId: pid,
        specRef: "spec-1",
      }),
      Layer.mergeAll(NoEvidenceProjectLive, MockGuardLive),
    )

    await expect(Effect.runPromise(program)).rejects.toBeDefined()
  })
})

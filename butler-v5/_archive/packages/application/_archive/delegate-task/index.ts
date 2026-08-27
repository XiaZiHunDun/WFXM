// application/delegate-task/delegate-task.ts
// 委派任务用例 — Spec 驱动 + 证据门控 [OPT-3][G-1]
// Phase 2 实现

import { Effect, Layer } from "effect"
import type { DelegateTaskInput, IntentReceipt, LoopError } from "@butler/domain"
import { ProjectService } from "@butler/ports"

// ─── delegateTask 用例 ──────────────────────────────────
export const delegateTask = (
  input: DelegateTaskInput,
): Effect.Effect<IntentReceipt, LoopError, ProjectService> =>
  Effect.gen(function* (_) {
    const proj = yield* _(ProjectService)

    // [OPT-3] 强制 Spec 引用
    yield* _(proj.loadSpec(input.specRef))

    // 实际委派
    const receipt = yield* _(proj.delegateTask(input))

    // [G-1] 证据门控：无证据即失败
    if (receipt.evidenceFiles.length === 0) {
      yield* _(
        Effect.fail({
          _tag: "GuardRejected",
          reason: { _tag: "MissingEvidence" },
        } as LoopError),
      )
    }

    return receipt
  })

// ─── Mock ProjectService Layer（测试用） ─────────────────
export const MockProjectServiceLive = Layer.succeed(
  ProjectService,
  ProjectService.of({
    loadSpec: () => Effect.succeed({}),
    delegateTask: (input) =>
      Effect.succeed({
        id: `receipt-${Date.now()}`,
        intent: `Task for project ${input.projectId}`,
        evidenceFiles: ["src/App.tsx", "src/App.test.tsx"],
        locDelta: { added: 50, removed: 10 },
        chainCompleteness: 1,
        guardFindings: [],
        authorAgent: "claude-3-5-sonnet",
        createdAt: Date.now(),
      }),
  }),
)

// application/run-workflow/run-workflow.ts
// 工作流编排用例 — Channel 多分支并行 [OPT-1]
// Phase 2 实现

import { Effect, Layer } from "effect"
import type { LinkedFilesSpec, LoopError } from "@butler/domain"
import { WorkflowService } from "@butler/ports"

// ─── runWorkflow 用例 ───────────────────────────────────
export const runWorkflow = (
  spec: LinkedFilesSpec,
): Effect.Effect<string, LoopError, WorkflowService> =>
  Effect.gen(function* (_) {
    const wf = yield* _(WorkflowService)
    const id = yield* _(wf.start(spec))

    // [OPT-1] Channel 多分支并行
    const channels = spec.expectedLinks.map((file) =>
      wf.send({
        toAgent: `coder-${file}`,
        message: `实现 ${file}`,
        contextRef: id,
      }),
    )
    yield* _(Effect.all(channels, { concurrency: "unbounded" }))

    // 合并结果
    yield* _(wf.merge(id))
    return id
  })

// ─── Mock WorkflowService Layer（测试用） ────────────────
export const MockWorkflowServiceLive = Layer.succeed(
  WorkflowService,
  WorkflowService.of({
    start: (_spec) => Effect.succeed(`wf-${Date.now()}`),
    send: (_cmd) => Effect.void,
    merge: (_id) => Effect.void,
  }),
)

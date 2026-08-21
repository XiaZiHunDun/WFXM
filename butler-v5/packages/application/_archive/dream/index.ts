// application/dream/dream.ts
// 记忆巩固用例 — Dream 两阶段 [OPT-7]
// Phase 2 实现

import { Effect, Layer } from "effect"
import type { DreamPhase, DreamResult } from "@butler/domain"
import { MemoryService } from "@butler/ports"

// ─── dream 用例 ─────────────────────────────────────────
export const dream = (phase: DreamPhase): Effect.Effect<DreamResult, never, MemoryService> =>
  Effect.gen(function* (_) {
    const mem = yield* _(MemoryService)
    return yield* _(mem.dream(phase))
  })

// ─── Mock MemoryService Layer（测试用） ──────────────────
export const MockMemoryServiceLive = Layer.succeed(
  MemoryService,
  MemoryService.of({
    search: (_q, _k) => Effect.succeed([]),
    dream: (phase) =>
      Effect.succeed({
        newMemories: [],
        prunedIds: [],
        phase,
      }),
  }),
)

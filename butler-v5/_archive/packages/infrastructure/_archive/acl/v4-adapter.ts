// infrastructure/acl/v4-adapter.ts
// ACL/V4 适配器 — 绞杀者模式反腐层
// Phase 4 实现

import { Effect, Layer } from "effect"
import type { IntentReceipt } from "@butler/domain"

// ─── 本地类型 ───────────────────────────────────────────
export type V4Message = {
  readonly convId: string
  readonly content: string
  readonly timestamp: number
}

export type Conversation = {
  readonly id: string
  readonly state: string
  readonly messages: readonly V4Message[]
}

// ─── V4Adapter Tag ──────────────────────────────────────
export class V4Adapter extends Effect.Tag("V4Adapter")<
  V4Adapter,
  {
    readonly importV4Conversation: (id: string) => Effect.Effect<Conversation>
    readonly exportV5Receipt: (r: IntentReceipt) => Effect.Effect<void>
    readonly subscribeMessages: () => Effect.Effect<readonly V4Message[]>
  }
>() {}

// ─── V4AdapterLive（Phase 4: 骨架，连接 v4 Python 进程） ──
export const V4AdapterLive = Layer.effect(
  V4Adapter,
  Effect.sync(() => {
    return V4Adapter.of({
      importV4Conversation: (id) =>
        Effect.succeed({
          id,
          state: "completed",
          messages: [],
        }),

      exportV5Receipt: (receipt) =>
        Effect.logInfo(`[V4Adapter] Exporting receipt ${receipt.id} to v4`),

      subscribeMessages: () => Effect.succeed([]),
    })
  }),
)

// ─── 测试用 Mock V4Adapter ──────────────────────────────
export const MockV4AdapterLive = Layer.succeed(
  V4Adapter,
  V4Adapter.of({
    importV4Conversation: (id) => Effect.succeed({ id, state: "completed", messages: [] }),
    exportV5Receipt: () => Effect.void,
    subscribeMessages: () => Effect.succeed([]),
  }),
)

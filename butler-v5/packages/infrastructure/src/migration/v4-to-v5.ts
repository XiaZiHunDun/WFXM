// infrastructure/migration/v4-to-v5.ts
// 数据迁移脚本 — v4 Python → v5 TypeScript
// Phase 4 实现

import { Effect } from "effect"
import type { ConversationEvent, LoopError } from "@butler/domain"

// ─── 迁移函数 ───────────────────────────────────────────
export const migrateConversations = (): Effect.Effect<readonly ConversationEvent[], LoopError> =>
  Effect.gen(function* () {
    // Phase 4: 从 v4 数据库/文件读取 conversation 历史
    // 转换为 v5 ConversationStarted + MessageAdded 事件流
    yield* Effect.logInfo("[Migration] Migrating v4 conversations...")
    return [] as readonly ConversationEvent[]
  })

export const migrateBlackboardCards = (): Effect.Effect<readonly ConversationEvent[], LoopError> =>
  Effect.gen(function* () {
    // Phase 4: 迁移 .blackboard/shifts → v5 IntentReceipts（authorAgent="v4-legacy"）
    yield* Effect.logInfo("[Migration] Migrating blackboard cards...")
    return [] as readonly ConversationEvent[]
  })

export const migrateV4ToV5 = (): Effect.Effect<
  { readonly conversations: number; readonly cards: number },
  LoopError
> =>
  Effect.gen(function* () {
    const convs = yield* migrateConversations()
    const cards = yield* migrateBlackboardCards()
    yield* Effect.logInfo(
      `[Migration] Complete: ${convs.length} conversations, ${cards.length} cards`,
    )
    return { conversations: convs.length, cards: cards.length }
  })

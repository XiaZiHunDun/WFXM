import { eq, isNull } from "drizzle-orm"
import { inferProjectIdFromConversationId } from "@butler/domain/runtime.js"
import type { ButlerDb } from "./db.js"
import { conversations } from "./schema.js"

/** Idempotently set project_id on rows that predate 0007. */
export async function backfillConversationProjectIds(db: ButlerDb): Promise<number> {
  const rows = await db
    .select({ conversationId: conversations.conversationId })
    .from(conversations)
    .where(isNull(conversations.projectId))
  let updated = 0
  for (const row of rows) {
    const projectId = inferProjectIdFromConversationId(row.conversationId)
    await db
      .update(conversations)
      .set({ projectId })
      .where(eq(conversations.conversationId, row.conversationId))
    updated += 1
  }
  return updated
}

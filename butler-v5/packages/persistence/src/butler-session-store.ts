import { eq } from "drizzle-orm"
import type {
  ButlerMessage,
  ButlerSessionRecord,
  ButlerSessionStore,
} from "@butler/ports/core/butler-session.js"
import type { ButlerDb } from "./db.js"
import { butlerSessions } from "./schema.js"

function toRecord(row: typeof butlerSessions.$inferSelect): ButlerSessionRecord {
  return {
    conversationId: row.conversationId,
    userId: row.userId,
    ...(row.projectId === null ? {} : { projectId: row.projectId }),
    messages: row.messages as readonly ButlerMessage[],
    ...(row.summary === null ? {} : { summary: row.summary }),
    createdAt: row.createdAt.toISOString(),
    updatedAt: row.updatedAt.toISOString(),
  }
}

/** Durable store for butler transcripts; agent-rag never reads these rows. */
export class DrizzleButlerSessionStore implements ButlerSessionStore {
  constructor(private readonly db: ButlerDb) {}

  async load(conversationId: string): Promise<ButlerSessionRecord | null> {
    const rows = await this.db
      .select()
      .from(butlerSessions)
      .where(eq(butlerSessions.conversationId, conversationId))
      .limit(1)
    const row = rows[0]
    return row ? toRecord(row) : null
  }

  async save(record: ButlerSessionRecord): Promise<void> {
    const values = {
      conversationId: record.conversationId,
      userId: record.userId,
      projectId: record.projectId ?? null,
      messages: record.messages,
      summary: record.summary ?? null,
      createdAt: new Date(record.createdAt),
      updatedAt: new Date(record.updatedAt),
    }
    await this.db
      .insert(butlerSessions)
      .values(values)
      .onConflictDoUpdate({
        target: butlerSessions.conversationId,
        set: {
          userId: values.userId,
          projectId: values.projectId,
          messages: values.messages,
          summary: values.summary,
          updatedAt: values.updatedAt,
        },
      })
  }

  async delete(conversationId: string): Promise<void> {
    await this.db.delete(butlerSessions).where(eq(butlerSessions.conversationId, conversationId))
  }
}

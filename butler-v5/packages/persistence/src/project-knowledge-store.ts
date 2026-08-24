import { desc, eq, sql } from "drizzle-orm"
import type {
  ProjectKnowledgeKind,
  ProjectKnowledgeProvenance,
  ProjectKnowledgeRecord,
} from "@butler/domain/knowledge/project-knowledge.js"
import type { ButlerDb } from "./db.js"
import { projectKnowledgeItems } from "./schema.js"

export interface ProjectKnowledgeStore {
  readonly create: (record: ProjectKnowledgeRecord) => Promise<ProjectKnowledgeRecord>
  readonly get: (itemId: string) => Promise<ProjectKnowledgeRecord | null>
  readonly delete: (itemId: string) => Promise<boolean>
  readonly listByProject: (input: {
    readonly projectId: string
    readonly limit?: number
  }) => Promise<readonly ProjectKnowledgeRecord[]>
  readonly deleteBySourceDocumentId: (documentId: string) => Promise<number>
}

function toRecord(row: typeof projectKnowledgeItems.$inferSelect): ProjectKnowledgeRecord {
  return {
    id: row.itemId,
    projectId: row.projectId,
    title: row.title,
    kind: row.kind as ProjectKnowledgeKind,
    body: row.body,
    byteSize: row.byteSize,
    provenance: (row.provenance ?? {}) as ProjectKnowledgeProvenance,
    createdAt: row.createdAt.getTime(),
    updatedAt: row.updatedAt.getTime(),
  }
}

export function createProjectKnowledgeStore(db: ButlerDb): ProjectKnowledgeStore {
  return {
    async create(record) {
      await db.insert(projectKnowledgeItems).values({
        itemId: record.id,
        projectId: record.projectId,
        title: record.title,
        kind: record.kind,
        body: record.body,
        byteSize: record.byteSize,
        provenance: record.provenance,
        createdAt: new Date(record.createdAt),
        updatedAt: new Date(record.updatedAt),
      })
      return record
    },

    async get(itemId) {
      const rows = await db
        .select()
        .from(projectKnowledgeItems)
        .where(eq(projectKnowledgeItems.itemId, itemId))
        .limit(1)
      const row = rows[0]
      return row ? toRecord(row) : null
    },

    async delete(itemId) {
      const deleted = await db
        .delete(projectKnowledgeItems)
        .where(eq(projectKnowledgeItems.itemId, itemId))
        .returning({ id: projectKnowledgeItems.itemId })
      return deleted.length > 0
    },

    async listByProject(input) {
      const limit = input.limit ?? 50
      const rows = await db
        .select()
        .from(projectKnowledgeItems)
        .where(eq(projectKnowledgeItems.projectId, input.projectId.trim()))
        .orderBy(desc(projectKnowledgeItems.updatedAt))
        .limit(limit)
      return rows.map(toRecord)
    },

    async deleteBySourceDocumentId(documentId) {
      const deleted = await db
        .delete(projectKnowledgeItems)
        .where(sql`${projectKnowledgeItems.provenance}->>'documentId' = ${documentId}`)
        .returning({ id: projectKnowledgeItems.itemId })
      return deleted.length
    },
  }
}

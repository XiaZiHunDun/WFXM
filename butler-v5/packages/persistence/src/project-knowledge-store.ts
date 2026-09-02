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
  readonly update: (record: ProjectKnowledgeRecord) => Promise<ProjectKnowledgeRecord>
  readonly get: (itemId: string) => Promise<ProjectKnowledgeRecord | null>
  readonly delete: (itemId: string) => Promise<boolean>
  readonly listByProject: (input: {
    readonly projectId: string
    readonly limit?: number
  }) => Promise<readonly ProjectKnowledgeRecord[]>
  readonly listAllProjects: () => Promise<readonly string[]>
  readonly listByProjects: (input: {
    readonly projectIds: readonly string[]
    readonly perProjectLimit?: number
  }) => Promise<readonly ProjectKnowledgeRecord[]>
  readonly findBySourcePath: (input: {
    readonly projectId: string
    readonly sourcePath: string
  }) => Promise<ProjectKnowledgeRecord | null>
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

    async update(record) {
      await db
        .update(projectKnowledgeItems)
        .set({
          title: record.title,
          kind: record.kind,
          body: record.body,
          byteSize: record.byteSize,
          provenance: record.provenance,
          updatedAt: new Date(record.updatedAt),
        })
        .where(eq(projectKnowledgeItems.itemId, record.id))
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
        .returning()
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

    async listAllProjects() {
      const rows = await db
        .selectDistinct({ projectId: projectKnowledgeItems.projectId })
        .from(projectKnowledgeItems)
      return rows
        .map((r) => r.projectId.trim())
        .filter((id) => id.length > 0)
        .sort()
    },

    async listByProjects(input) {
      const ids = [...new Set(input.projectIds.map((id) => id.trim()).filter((id) => id.length > 0))]
      const results: ProjectKnowledgeRecord[] = []
      for (const projectId of ids) {
        results.push(...(await this.listByProject({ projectId, limit: input.perProjectLimit })))
      }
      return results
    },

    async findBySourcePath(input) {
      const projectId = input.projectId.trim()
      const sourcePath = input.sourcePath.trim()
      if (!projectId || !sourcePath) return null
      const rows = await db
        .select()
        .from(projectKnowledgeItems)
        .where(
          sql`${projectKnowledgeItems.projectId} = ${projectId} AND ${projectKnowledgeItems.provenance}->>'sourcePath' = ${sourcePath}`,
        )
        .orderBy(desc(projectKnowledgeItems.updatedAt))
        .limit(1)
      const row = rows[0]
      return row ? toRecord(row) : null
    },

    async deleteBySourceDocumentId(documentId) {
      const deleted = await db
        .delete(projectKnowledgeItems)
        .where(sql`${projectKnowledgeItems.provenance}->>'documentId' = ${documentId}`)
        .returning()
      return deleted.length
    },
  }
}

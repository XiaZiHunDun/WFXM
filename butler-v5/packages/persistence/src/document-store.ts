import { desc, eq } from "drizzle-orm"
import type {
  DocumentFormat,
  DocumentProvenance,
  DocumentRecord,
  DocumentStatus,
} from "@butler/domain/knowledge/document-ingest.js"
import type { ButlerDb } from "./db.js"
import { documents } from "./schema.js"

export interface DocumentStore {
  readonly create: (record: DocumentRecord) => Promise<DocumentRecord>
  readonly get: (documentId: string) => Promise<DocumentRecord | null>
  readonly delete: (documentId: string) => Promise<boolean>
  readonly listBySubject: (input: {
    readonly subject: string
    readonly limit?: number
  }) => Promise<readonly DocumentRecord[]>
}

function toRecord(row: typeof documents.$inferSelect): DocumentRecord {
  return {
    id: row.documentId,
    subject: row.subject,
    title: row.title,
    format: row.format as DocumentFormat,
    mimeType: row.mimeType,
    byteSize: row.byteSize,
    extractedText: row.extractedText,
    status: row.status as DocumentStatus,
    failureReason: row.failureReason,
    provenance: (row.provenance ?? {}) as DocumentProvenance,
    createdAt: row.createdAt.getTime(),
    updatedAt: row.updatedAt.getTime(),
  }
}

export function createDocumentStore(db: ButlerDb): DocumentStore {
  return {
    async create(record) {
      await db.insert(documents).values({
        documentId: record.id,
        subject: record.subject,
        title: record.title,
        format: record.format,
        mimeType: record.mimeType,
        byteSize: record.byteSize,
        extractedText: record.extractedText,
        status: record.status,
        failureReason: record.failureReason,
        provenance: record.provenance,
        createdAt: new Date(record.createdAt),
        updatedAt: new Date(record.updatedAt),
      })
      return record
    },

    async get(documentId) {
      const rows = await db
        .select()
        .from(documents)
        .where(eq(documents.documentId, documentId))
        .limit(1)
      const row = rows[0]
      return row ? toRecord(row) : null
    },

    async delete(documentId) {
      const deleted = await db
        .delete(documents)
        .where(eq(documents.documentId, documentId))
        .returning({ id: documents.documentId })
      return deleted.length > 0
    },

    async listBySubject(input) {
      const limit = input.limit ?? 50
      const rows = await db
        .select()
        .from(documents)
        .where(eq(documents.subject, input.subject))
        .orderBy(desc(documents.updatedAt))
        .limit(limit)
      return rows.map(toRecord)
    },
  }
}

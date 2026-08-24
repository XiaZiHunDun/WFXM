import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"

const MIGRATION_FILES = [
  "0001_initial.sql",
  "0002_target_runtime.sql",
  "0003_scoped_grant_fields.sql",
  "0004_durable_memory.sql",
  "0005_documents.sql",
  "0006_task_procedure.sql",
  "0007_conversation_project_id.sql",
  "0008_conversation_id_text.sql",
  "0009_sandbox_network_allowlist.sql",
  "0010_project_knowledge.sql",
] as const

export type MigrationFileName = (typeof MIGRATION_FILES)[number]

/** Ordered migration filenames applied by openButlerDatabase / makeTestDb. */
export function listMigrationFiles(): readonly MigrationFileName[] {
  return MIGRATION_FILES
}

function readMigration(name: MigrationFileName): string {
  return readFileSync(fileURLToPath(new URL(`./${name}`, import.meta.url)), "utf8")
}

/** Ordered SQL migrations applied to fresh and existing databases. */
export function migrationSql(): string {
  return MIGRATION_FILES.map(readMigration).join("\n")
}

export async function applyMigrations(exec: (sql: string) => Promise<unknown>): Promise<void> {
  for (const name of MIGRATION_FILES) {
    await exec(readMigration(name))
  }
}

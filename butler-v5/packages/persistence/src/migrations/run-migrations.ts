import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"

const MIGRATION_FILES = ["0001_initial.sql", "0002_target_runtime.sql"] as const

function readMigration(name: (typeof MIGRATION_FILES)[number]): string {
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

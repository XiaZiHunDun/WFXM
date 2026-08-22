import { describe, expect, it } from "vitest"
import { listMigrationFiles, migrationSql } from "./run-migrations.js"

describe("migrations registry", () => {
  it("includes P4 knowledge/task migrations in order", () => {
    const files = listMigrationFiles()
    expect(files.indexOf("0004_durable_memory.sql")).toBeLessThan(
      files.indexOf("0005_documents.sql"),
    )
    expect(files.indexOf("0005_documents.sql")).toBeLessThan(
      files.indexOf("0006_task_procedure.sql"),
    )
    const sql = migrationSql()
    expect(sql).toContain("durable_memories")
    expect(sql).toContain("CREATE TABLE IF NOT EXISTS documents")
    expect(sql).toContain("CREATE TABLE IF NOT EXISTS procedures")
    expect(sql).toContain("CREATE TABLE IF NOT EXISTS tasks")
  })
})

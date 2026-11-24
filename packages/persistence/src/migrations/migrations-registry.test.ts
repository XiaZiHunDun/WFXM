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
    expect(sql).toContain("CREATE TABLE IF NOT EXISTS project_knowledge_items")
    expect(sql).toContain("CREATE TABLE IF NOT EXISTS task_sessions")
    expect(sql).toContain("CREATE TABLE IF NOT EXISTS butler_sessions")
    expect(sql).toContain("CREATE TABLE IF NOT EXISTS reminders")
  })

  it("includes D2.2 scoped_grants capability column migration", () => {
    const files = listMigrationFiles()
    expect(files).toContain("0011_scoped_grant_capability_column.sql")
    const sql = migrationSql()
    expect(sql).toContain("ALTER TABLE scoped_grants")
    expect(sql).toContain("ADD COLUMN IF NOT EXISTS capability")
    expect(sql).toContain("scoped_grants_capability_idx")
  })

  it("includes Phase 5 P0 trace_events migration with indexes", () => {
    const files = listMigrationFiles()
    expect(files).toContain("0018_trace_events.sql")
    const sql = migrationSql()
    expect(sql).toContain("CREATE TABLE IF NOT EXISTS trace_events")
    expect(sql).toContain("trace_events_created_idx")
    expect(sql).toContain("trace_events_run_idx")
    expect(sql).toContain("trace_events_conversation_idx")
    expect(sql).toContain("trace_events_turn_idx")
    expect(sql).toContain("trace_events_kind_idx")
  })
})

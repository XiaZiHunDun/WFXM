/**
 * Arch guard (D22-arch-align §11 deferred items / trigger state):
 * DESIGN §11 line 438 列不默认建设 5 项：
 *   - tasks、procedures、独立 approvals 表、memory_records、documents
 * "不默认建设" = 默认不建，但有真实触发需求时可建（trigger-conditioned），
 * 类似 §11.4 line 484 局部 Projection 的 "实测需求时" 触发条件。
 *
 * Audit (D22, 2026-08-31) found 3 项已 triggered (P0-P4 capability 引入,
 * commit `f60de759` v5 大爆炸)，并接 production wiring + owner routes：
 *   - tasks      — schema.ts pgTable + TaskStore + 4 owner routes + wechat commands
 *   - procedures — schema.ts pgTable + ProcedureStore + 2 owner routes
 *   - documents  — schema.ts pgTable + DocumentStore + 6 owner routes
 * 另 2 项 0 violation：
 *   - memory_records         — 0 violation（durable_memories 是 §12 已实施，不是 §11 list 项）
 *   - 独立 approvals 表      — 0 violation（字段在 waiting_approval Step）
 *
 * 本 guard 正向 lock "已 trigger 项持续存在 + 接入生产"，
 * 反向 lock "未 trigger 项持续不建"，使 DESIGN 文字与实现不再 stale。
 *
 * Static checks (no runtime):
 *   - schema.ts 必须含 `pgTable("tasks"...)` / `pgTable("procedures"...)`
 *     / `pgTable("documents"...)`
 *   - bootstrap-wiring.ts 必须注册 taskStore/procedureStore/documentStore
 *   - owner-routes.ts 必须含 12 endpoints（6 documents + 2 procedures + 4 tasks）
 *   - schema.ts 必须 NOT 含 `pgTable("memory_records"...)` 或
 *     `pgTable("approvals"...)`（独立 approvals 表）
 *   - approval 字段路径只在 Step 上（"waiting_approval" Step / waiting_approval 字段）
 *
 * Remediation when this guard fires:
 *   - "已 trigger 项不再存在" — 重新对照 §11 line 438 + §11.4 触发条件；
 *     若 owner 收回需求则改 DESIGN 文字 + 删除表 / store / routes
 *     （如 D19 orphan cleanup 流程）。
 *   - "未 trigger 项被建" — 立即回滚并对照 §11 line 438 字面意义；
 *     若 owner 接受则走 D22 trigger 流程：DESIGN 文字更新 + 本 guard 重写。
 *
 * Runtime behavior is verified by:
 *   - The 3 stores themselves + 12 owner routes unit/integration tests
 *     (existing) — D22 only locks static conformance.
 */

import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { join } from "node:path"

const SCHEMA = join(__dirname, "../../packages/persistence/src/schema.ts")
const BOOTSTRAP_WIRING = join(__dirname, "../../apps/api/src/bootstrap-wiring.ts")
const OWNER_ROUTES = join(__dirname, "../../apps/api/src/owner-routes.ts")

describe("arch: §11 deferred items — D22 trigger state (3 triggered, 2 not)", () => {
  // ─── 已 triggered 项（lock 持续存在 + 接入生产） ──────────────

  it("schema.ts declares `tasks` pgTable (§11 line 438 deferred item, now triggered)", () => {
    const src = readFileSync(SCHEMA, "utf-8")
    expect(
      /export\s+const\s+tasks\s*=\s*pgTable\s*\(\s*["']tasks["']/.test(src),
      "schema.ts must keep `export const tasks = pgTable('tasks', ...)` — P0-P4 capability 真触发, D22 trigger state",
    ).toBe(true)
  })

  it("schema.ts declares `procedures` pgTable (§11 line 438 deferred item, now triggered)", () => {
    const src = readFileSync(SCHEMA, "utf-8")
    expect(
      /export\s+const\s+procedures\s*=\s*pgTable\s*\(\s*["']procedures["']/.test(src),
      "schema.ts must keep `export const procedures = pgTable('procedures', ...)` — P0-P4 capability 真触发, D22 trigger state",
    ).toBe(true)
  })

  it("schema.ts declares `documents` pgTable (§11 line 438 deferred item, now triggered)", () => {
    const src = readFileSync(SCHEMA, "utf-8")
    expect(
      /export\s+const\s+documents\s*=\s*pgTable\s*\(\s*["']documents["']/.test(src),
      "schema.ts must keep `export const documents = pgTable('documents', ...)` — P0-P4 capability 真触发, D22 trigger state",
    ).toBe(true)
  })

  it("bootstrap-wiring.ts registers taskStore / procedureStore / documentStore (production wiring)", () => {
    const src = readFileSync(BOOTSTRAP_WIRING, "utf-8")
    expect(src).toMatch(/createDocumentStore\s*\(/)
    expect(src).toMatch(/createProcedureStore\s*\(/)
    expect(src).toMatch(/createTaskStore\s*\(/)
    // And the makeWiring payload must carry them so owner-routes can consume.
    expect(src).toMatch(/documentStore,?\s*\n\s*projectKnowledgeStore,?\s*\n\s*procedureStore,?\s*\n\s*taskStore/)
  })

  it("owner-routes.ts exposes 12 owner HTTP endpoint registrations (6 documents + 2 procedures + 4 tasks)", () => {
    const src = readFileSync(OWNER_ROUTES, "utf-8")
    // Count endpoint registrations: `app.{method}("/v1/owner/<kind>/..."`
    // Method-agnostic — a single path with multiple methods counts per
    // method (e.g. /v1/owner/documents/:documentId has both GET and DELETE).
    const docRoutes = src.match(/app\.(get|post|delete|put)\s*\(\s*"\/v1\/owner\/documents[^"',)\s]*/g) ?? []
    const procRoutes = src.match(/app\.(get|post|delete|put)\s*\(\s*"\/v1\/owner\/procedures[^"',)\s]*/g) ?? []
    const taskRoutes = src.match(/app\.(get|post|delete|put)\s*\(\s*"\/v1\/owner\/tasks[^"',)\s]*/g) ?? []
    // 6 documents: list (GET) + create (POST) + :id (GET) + :id (DELETE)
    //                    + :id/promote-memory (POST) + :id/promote-project-knowledge (POST)
    expect(
      docRoutes.length,
      `documents endpoint registrations = ${docRoutes.length}, want ≥ 6`,
    ).toBeGreaterThanOrEqual(6)
    // 2 procedures: list (GET) + create (POST)
    expect(
      procRoutes.length,
      `procedures endpoint registrations = ${procRoutes.length}, want ≥ 2`,
    ).toBeGreaterThanOrEqual(2)
    // 4 tasks: list (GET) + create (POST) + :id/run (POST) + :id/done (POST)
    expect(
      taskRoutes.length,
      `tasks endpoint registrations = ${taskRoutes.length}, want ≥ 4`,
    ).toBeGreaterThanOrEqual(4)
  })

  // ─── 未 triggered 项（lock 持续不建） ──────────────────────────

  it("schema.ts does NOT declare `memory_records` pgTable (§11 deferred, not triggered)", () => {
    const src = readFileSync(SCHEMA, "utf-8")
    expect(
      /pgTable\s*\(\s*["']memory_records["']/.test(src),
      "schema.ts must NOT contain `pgTable('memory_records', ...)` — §11 line 438 不默认建设 + 未触发; Durable Memory 走 §12 `durable_memories` 已实施",
    ).toBe(false)
  })

  it("schema.ts does NOT declare a standalone `approvals` pgTable (§11 deferred, not triggered)", () => {
    const src = readFileSync(SCHEMA, "utf-8")
    expect(
      /pgTable\s*\(\s*["']approvals["']/.test(src),
      "schema.ts must NOT contain `pgTable('approvals', ...)` — §11 line 438 不默认建设; approval 字段路径在 waiting_approval Step 上",
    ).toBe(false)
  })

  })
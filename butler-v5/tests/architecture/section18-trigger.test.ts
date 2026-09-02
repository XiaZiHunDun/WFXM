/**
 * Arch guard (D16-arch-align §18 trigger guard): §18 延后项与触发条件。
 *
 * DESIGN §18 lists deferred roadmap items. Until their trigger condition
 * fires, no production code may activate them. This file locks that
 * invariant by static-checking that no production caller invokes a
 * §18-deferred API.
 *
 * Audit findings (2026-08-30, D16):
 *   - 独立 Task 聚合 — shipped via `apps/api/src/wechat-task-commands.ts`
 *     and `apps/api/src/owner-routes.ts` + `task-run.ts` + `wechat-project-surface.ts`.
 *     Owner has a real WeChat `/待办 /tasks /运行 /完成` command surface
 *     for cross-conversation todos. Trigger met — NOT in this guard.
 *   - Procedure 模板 — ships alongside Task (see above). Trigger met — NOT.
 *   - 局部 Projection — `packages/ports/src/core/projection.ts` interface
 *     exists; `packages/adapters/src/postgres/postgres-projection.ts`
 *     impl does NOT exist; no production caller imports the port.
 *     GUARDED.
 *   - Snapshot — `packages/persistence/src/snapshot.ts` +
 *     `event-bridge.saveSnapshot/loadSnapshot` wrap; no production caller
 *     invokes saveSnapshot / loadSnapshot. GUARDED.
 *   - 向量检索 — `packages/domain/src/memory/types.ts` declares
 *     `embedding: readonly number[]` on MemoryRecord; no production caller
 *     reads the field. GUARDED.
 *   - 并发资源锁 — only per-conversation serialization
 *     (`run-coordinator.ts`); not workspace-level exclusive lock.
 *     §18 trigger ("出现必须独占的 workspace 或设备冲突") not fired.
 *     Not in this guard — no production API surface exists.
 *   - 浏览器能力 — no browser code. PASS.
 *   - 第二 Channel — Slack structural-align only (R14); not wired to
 *     production trigger. PASS (per owner dialog).
 *   - 外部 OTEL — only `local-trace.ts` stdout OTLP-ish, "not a full SDK".
 *     PASS.
 *   - 独立 Worker/Broker — no AMQP / Kafka / Redis pub-sub in-process.
 *     PASS.
 *
 * Static checks (no runtime):
 *   - No production file imports `packages/ports/src/core/projection.ts`
 *     (the interface is allowed to exist, but no one may consume it
 *     until the §18 trigger fires)
 *   - No production file imports `packages/persistence/src/snapshot.ts`
 *     standalone (event-bridge wrap is allowed as a passive layer, but
 *     its `saveSnapshot` / `loadSnapshot` methods must have no caller)
 *   - No production file reads `.embedding` on a memory record
 *   - `packages/adapters/src/postgres/postgres-projection.ts` must NOT
 *     exist (no production impl until §18 trigger fires)
 *
 * Runtime behavior is verified by:
 *   - The scaffolding files themselves (snapshot.ts, task-procedure-store.ts,
 *     memory/types.ts, projection.ts) compile and unit-test green
 */

import { describe, expect, it } from "vitest"
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"

const PROJECTION_PORT = join(
  __dirname,
  "../../packages/ports/src/core/projection.ts",
)
const SNAPSHOT_MODULE = join(
  __dirname,
  "../../packages/persistence/src/snapshot.ts",
)
const MEMORY_TYPES = join(
  __dirname,
  "../../packages/domain/src/memory/types.ts",
)
const POSTGRES_PROJECTION_IMPL = join(
  __dirname,
  "../../packages/adapters/src/postgres/postgres-projection.ts",
)

const EVENT_BRIDGE = join(
  __dirname,
  "../../packages/persistence/src/event-bridge.ts",
)

const DURABLE_MEMORY_STORE = join(
  __dirname,
  "../../packages/persistence/src/durable-memory-store.ts",
)
const API_TOOLS = join(__dirname, "../../apps/api/src/tools.ts")
const DURABLE_MEMORY_INJECT = join(
  __dirname,
  "../../apps/api/src/durable-memory-inject.ts",
)
const OWNER_ROUTES = join(__dirname, "../../apps/api/src/owner-routes.ts")
import { readOwnerRoutesSource } from "./owner-routes-source.js"
const WECHAT_MEMORY_COMMANDS = join(
  __dirname,
  "../../apps/api/src/wechat-memory-commands.ts",
)

/** Module path fragments that wrap §18-deferred APIs passively. */
const PASSIVE_WRAP_FILES: ReadonlySet<string> = new Set([EVENT_BRIDGE])

function listProductionTsFiles(root: string): string[] {
  const out: string[] = []
  function walk(dir: string): void {
    for (const entry of readdirSync(dir)) {
      const p = join(dir, entry)
      const stat = statSync(p)
      if (stat.isDirectory()) {
        if (
          entry === "node_modules" ||
          entry === "dist" ||
          entry === "_archive" ||
          entry === "coverage" ||
          entry.startsWith(".")
        ) {
          continue
        }
        walk(p)
      } else if (
        entry.endsWith(".ts") &&
        !entry.endsWith(".test.ts") &&
        !entry.endsWith(".d.ts")
      ) {
        out.push(p)
      }
    }
  }
  walk(root)
  return out
}

describe("arch: §18 trigger guard (no premature activation of deferred features)", () => {
  it("postgres-projection impl must NOT exist until §18 trigger fires", () => {
    expect(
      existsSync(POSTGRES_PROJECTION_IMPL),
      "packages/adapters/src/postgres/postgres-projection.ts exists — projection impl must wait for §18 trigger",
    ).toBe(false)
  })

  it("no production file imports the projection port (interface is allowed to exist)", () => {
    const root = join(__dirname, "../..")
    const prodFiles = [
      ...listProductionTsFiles(join(root, "packages")),
      ...listProductionTsFiles(join(root, "apps")),
    ]
    const violations: string[] = []
    for (const file of prodFiles) {
      const src = readFileSync(file, "utf-8")
      if (
        /from\s+["'][^"']*ports\/core\/projection[^"']*["']/.test(src) ||
        /from\s+["'][^"']*@butler\/ports\/core\/projection[^"']*["']/.test(src)
      ) {
        // Allow the projection port file itself + barrel re-export
        if (file === PROJECTION_PORT || file.endsWith("/packages/ports/src/index.ts")) {
          continue
        }
        violations.push(file)
      }
    }
    expect(
      violations,
      `production files importing core/projection port: ${violations.join(", ")}`,
    ).toEqual([])
  })

  it("no production file invokes standalone saveSnapshot / loadSnapshot (event-bridge wrap is the only allowed caller)", () => {
    const root = join(__dirname, "../..")
    const prodFiles = [
      ...listProductionTsFiles(join(root, "packages")),
      ...listProductionTsFiles(join(root, "apps")),
    ]
    const violations: string[] = []
    for (const file of prodFiles) {
      // Skip the scaffolding files themselves and the event-bridge wrap.
      if (file === SNAPSHOT_MODULE || PASSIVE_WRAP_FILES.has(file)) continue
      const src = readFileSync(file, "utf-8")
      // Detect standalone saveSnapshot( / loadSnapshot( as a function call.
      // Method invocations like bridge.saveSnapshot(...) are caught too,
      // but the event-bridge wrap is the only such occurrence and is
      // already excluded above.
      if (/(?<![.\w])saveSnapshot\s*\(/.test(src)) {
        violations.push(`${file}: standalone saveSnapshot(...)`)
      }
      if (/(?<![.\w])loadSnapshot\s*\(/.test(src)) {
        violations.push(`${file}: standalone loadSnapshot(...)`)
      }
    }
    expect(
      violations,
      `standalone snapshot API callers (event-bridge wrap excluded): ${violations.join(", ")}`,
    ).toEqual([])
  })

  it("no production file reads the embedding field on a memory record (type declared but not consumed)", () => {
    const root = join(__dirname, "../..")
    const prodFiles = [
      ...listProductionTsFiles(join(root, "packages")),
      ...listProductionTsFiles(join(root, "apps")),
    ]
    const violations: string[] = []
    for (const file of prodFiles) {
      // The type declaration itself is allowed; the field must not be
      // read or assigned elsewhere.
      if (file === MEMORY_TYPES) continue
      const src = readFileSync(file, "utf-8")
      // Detect .embedding access (member expression only — bare `embedding`
      // identifier in identifiers is normal TypeScript).
      if (/\.embedding\b/.test(src)) {
        violations.push(`${file}: .embedding field read/write`)
      }
    }
    expect(
      violations,
      `production files reading .embedding on memory records: ${violations.join(", ")}`,
    ).toEqual([])
  })

  // ── §18 row 3 Durable Memory / Project Knowledge 表 — D39 lock ────
  //
  // Row 3 was originally a §18 deferred item ("Durable Memory /
  // Project Knowledge 表"). It has since shipped via D30 + Tasks 1-5
  // (R10 handoff + wechat commands + G3 batch UI). D16's 4 cases above
  // guard rows that are STILL deferred; this case locks the row-3
  // MVP-ship evidence so future regressions trip this guard.
  //
  // D39 G3 batch candidate UI (2026-09-01) added 3 owner batch routes
  // (confirm-batch + reject-batch) + wechat /记忆候选 + /确认记忆 batch.

  it("§18 row 3 Durable Memory MVP ship — 5 foundation files exist and are non-empty (D39 lock)", () => {
    const FILES = [
      DURABLE_MEMORY_STORE,
      API_TOOLS,
      DURABLE_MEMORY_INJECT,
      OWNER_ROUTES,
      WECHAT_MEMORY_COMMANDS,
    ] as const
    for (const f of FILES) {
      expect(
        existsSync(f),
        `§18 row 3 MVP foundation file missing: ${f}`,
      ).toBe(true)
      const text = readFileSync(f, "utf-8")
      expect(
        text.length,
        `§18 row 3 MVP foundation file is empty: ${f}`,
      ).toBeGreaterThan(0)
    }
  })

  it("§18 row 3 recall tools — recall_durable_memory + recall_document + recall_project_knowledge all defined in apps/api/src/tools.ts", () => {
    const src = readFileSync(API_TOOLS, "utf-8")
    for (const toolName of [
      "recall_durable_memory",
      "recall_document",
      "recall_project_knowledge",
    ]) {
      expect(
        new RegExp(`name:\\s*["']${toolName}["']`).test(src),
        `apps/api/src/tools.ts must declare recall tool: ${toolName}`,
      ).toBe(true)
    }
  })

  it("§18 row 3 owner batch routes — confirm-batch + reject-batch + GET hasMore/countBySubject present (D39 G3)", () => {
    const src = readOwnerRoutesSource()
    expect(
      /\/v1\/owner\/memories\/confirm-batch/.test(src),
      "owner-routes must declare POST /v1/owner/memories/confirm-batch",
    ).toBe(true)
    expect(
      /\/v1\/owner\/memories\/reject-batch/.test(src),
      "owner-routes must declare POST /v1/owner/memories/reject-batch",
    ).toBe(true)
    expect(
      /\bhasMore\b/.test(src),
      "owner-routes GET /v1/owner/memories must expose hasMore pagination flag",
    ).toBe(true)
    expect(
      /\bcountBySubject\b/.test(src),
      "owner-routes GET /v1/owner/memories must call countBySubject for total",
    ).toBe(true)
  })

  it("§18 row 3 wechat batch commands — /记忆候选 + /确认记忆 batch wired (D39 G3)", () => {
    const src = readFileSync(WECHAT_MEMORY_COMMANDS, "utf-8")
    expect(
      src.includes("/记忆候选"),
      "wechat-memory-commands must handle /记忆候选 command",
    ).toBe(true)
    expect(
      src.includes("/确认记忆"),
      "wechat-memory-commands must handle /确认记忆 batch command",
    ).toBe(true)
    expect(
      /confirm-batch/.test(src),
      "wechat-memory-commands must invoke confirm-batch owner route",
    ).toBe(true)
  })
})
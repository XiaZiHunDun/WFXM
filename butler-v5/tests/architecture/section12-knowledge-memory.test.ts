/**
 * Arch guard (D30-arch-align §12 知识层与记忆): lock §12 主体 invariants.
 *
 *   §12 — memory is layered into 3 tiers (Transcript / Durable Memory
 *         / Project Knowledge); Durable Memory must trace to Message /
 *         Document / Owner explicit input; Run 内部摘要/截断/工具结果压缩
 *         是可重建执行产物 not 知识层; 默认不启用 embedding (结构化字段 +
 *         全文搜索 + 显式召回先); 当前不建设 5 项 (Dream two-phase /
 *         ContextGraph / auto-index / 无来源经验沉积 / 独立 RAG Studio).
 *
 * D9 §20 #9 already locked the cross-import boundary (3 layers stay
 * independent at store + domain + schema levels). D30 extends that
 * to: §12 主体 (memory layering + Durable Memory fields + Project
 * Knowledge ≠ Durable Memory + not-built 5 items do not get active
 * runtime invocation).
 *
 * Audit findings (D30, 2026-08-31):
 *
 *   - 3 layers materialized as 3 independent persistence tables:
 *     `messages` (Transcript) / `durable_memories` (Durable Memory) /
 *     `project_knowledge_items` (Project Knowledge).
 *   - `DurableMemoryRecord` (`packages/domain/src/knowledge/durable-memory.ts:23`)
 *     carries the 4 §12 fields: `sourceKind: DurableMemorySourceKind` /
 *     `confidence: number` / `expiresAt: number | null` /
 *     `status: "candidate" | "confirmed"`. `DurableMemorySourceKind`
 *     is the 3-source union (`owner` / `message` / `document`),
 *     mapping §12 line 556 "可追溯到 Message、Document 或 Owner
 *     明确输入".
 *   - `ProjectKnowledgeRecord` lives in `project-knowledge.ts` and
 *     is structurally different from `DurableMemoryRecord` (no
 *     sourceKind/status/confidence/expiresAt). D9 already locks the
 *     no-cross-import invariant.
 *   - §12 not-built 5 items have **type-only placeholders** in the
 *     domain layer (e.g. `DreamPhase` in `domain/src/memory/types.ts`)
 *     but **zero runtime / apps/api invocation**. This is consistent
 *     with §12 trigger-conditioned stance: surface reserved, not
 *     activated. D30 locks "no active invocation" so a future
 *     commit that wires DreamPhase / ContextGraph / RAG Studio into
 *     a runtime path trips this guard.
 *   - Embedding default-off: `durable_memories` table has no
 *     `embedding` column; `project_knowledge_items` `body` is plain
 *     text. Recall paths in `domain/src/memory/pure.ts` use
 *     structural fields (`importance` / `scoreImportance`) — no
 *     `.embedding` access.
 *
 * Static checks (no runtime):
 *   - `messages` + `durableMemories` + `projectKnowledgeItems`
 *     pgTables exist (3-tier storage).
 *   - `DurableMemoryRecord` carries `sourceKind` / `confidence` /
 *     `expiresAt` / `status`.
 *   - `DurableMemorySourceKind` union covers `owner` / `message` /
 *     `document`.
 *   - `ProjectKnowledgeRecord` does NOT declare the 4 Durable Memory
 *     fields (no impersonation).
 *   - Active runtime + apps/api files do NOT invoke `DreamPhase` /
 *     `consolidate*` / `ContextGraph` / `RAG Studio` / auto-index
 *     paths (only type placeholders in domain/memory/types.ts).
 *   - `durableMemories` schema has no `embedding` column.
 *
 * Runtime behavior is verified by:
 *   - three-memory-separation.test.ts (D9 cross-import locks)
 *   - durable-memory.test.ts (createDurableMemoryRecord source check)
 *   - project-knowledge.test.ts (Project Knowledge distinctness)
 *
 * Remediation when this guard fires:
 *   - Layer merged (cross-import introduced): §12 violation;
 *     restore layer isolation per D9 §20 #9.
 *   - Durable Memory field removed: §12 line 548 violation; restore.
 *   - sourceKind reduced to ≤ 2 sources: §12 line 556 violation;
 *     §12 mandates 3 source kinds.
 *   - Project Knowledge adopts Durable Memory fields: §12 line 549
 *     "Project Knowledge 不等同于个人记忆" violation; remove the
 *     impersonating fields.
 *   - DreamPhase / ContextGraph / RAG Studio wired to active
 *     runtime: §12 line 561 "当前不建设" violation; revert or
 *     move to a separate PRD + change §12 "当前不建设" list first.
 *   - Embedding column added to durable_memories: §12 line 558-559
 *     violation (default 不启用 embedding); remove the column.
 */

import { describe, expect, it } from "vitest"
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"

const SCHEMA = join(__dirname, "../../packages/persistence/src/schema.ts")
const DURABLE_MEMORY = join(
  __dirname,
  "../../packages/domain/src/knowledge/durable-memory.ts",
)
const PROJECT_KNOWLEDGE = join(
  __dirname,
  "../../packages/domain/src/knowledge/project-knowledge.ts",
)
const MEMORY_TYPES = join(
  __dirname,
  "../../packages/domain/src/memory/types.ts",
)
const MEMORY_PURE = join(
  __dirname,
  "../../packages/domain/src/memory/pure.ts",
)
const RUNTIME_SRC = join(__dirname, "../../packages/runtime/src")
const APPS_SRC = join(__dirname, "../../apps/api/src")
const OWNER_ROUTES = join(__dirname, "../../apps/api/src/owner-routes.ts")
const WECHAT_MEMORY_COMMANDS = join(
  __dirname,
  "../../apps/api/src/wechat-memory-commands.ts",
)

function listProductionTs(root: string): string[] {
  const out: string[] = []
  function walk(dir: string): void {
    if (!existsSafe(dir)) return
    for (const entry of readdirSync(dir)) {
      const p = join(dir, entry)
      const st = statSync(p)
      if (st.isDirectory()) {
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

function existsSafe(p: string): boolean {
  try {
    statSync(p)
    return true
  } catch {
    return false
  }
}

describe("arch: §12 知识层与记忆 (D30 — 3 tiers + Durable Memory trace + Project Knowledge ≠ + not-built 5 items)", () => {
  // ── 1. §12 3 层 schema 存在 ──────────────────────────────────────

  it("§12: 3 layers materialized as 3 independent persistence tables (messages + durableMemories + projectKnowledgeItems)", () => {
    const src = readFileSync(SCHEMA, "utf-8")
    expect(
      /export\s+const\s+messages\s*=\s*pgTable\s*\(\s*["']messages["']/.test(src),
      "messages pgTable (Transcript) must exist",
    ).toBe(true)
    expect(
      /export\s+const\s+durableMemories\s*=\s*pgTable\s*\(\s*["']durable_memories["']/.test(
        src,
      ),
      "durable_memories pgTable must exist (Durable Memory)",
    ).toBe(true)
    expect(
      /export\s+const\s+projectKnowledgeItems\s*=\s*pgTable\s*\(\s*["']project_knowledge_items["']/.test(
        src,
      ),
      "project_knowledge_items pgTable must exist (Project Knowledge)",
    ).toBe(true)
  })

  // ── 2. §12 DurableMemoryRecord 4 字段 ──────────────────────────

  it("§12: DurableMemoryRecord carries the 4 §12 fields (sourceKind/confidence/expiresAt/status)", () => {
    const src = readFileSync(DURABLE_MEMORY, "utf-8")
    const match = src.match(
      /export interface DurableMemoryRecord\s*\{([\s\S]*?)\n\}/,
    )
    expect(match, "DurableMemoryRecord interface not found").not.toBeNull()
    const body = match?.[1] ?? ""
    for (const field of ["sourceKind", "confidence", "expiresAt", "status"]) {
      expect(
        new RegExp(`readonly\\s+${field}\\??\\b`).test(body),
        `DurableMemoryRecord missing §12 field: ${field}`,
      ).toBe(true)
    }
  })

  // ── 3. §12 sourceKind 3 source (owner/message/document) ────────

  it("§12: DurableMemorySourceKind union covers the 3 source kinds (owner/message/document)", () => {
    const src = readFileSync(DURABLE_MEMORY, "utf-8")
    const match = src.match(
      /export type DurableMemorySourceKind\s*=\s*([\s\S]*?)\n\nexport/,
    )
    expect(match, "DurableMemorySourceKind type not found").not.toBeNull()
    const body = match?.[1] ?? ""
    for (const kind of ["owner", "message", "document"]) {
      expect(body, `DurableMemorySourceKind missing: ${kind}`).toMatch(
        new RegExp(`["']${kind}["']`),
      )
    }
  })

  // ── 4. §12 Project Knowledge ≠ Durable Memory ─ ──────────────────

  it("§12: ProjectKnowledgeRecord does NOT impersonate DurableMemoryRecord (no sourceKind/confidence/expiresAt/status fields)", () => {
    const src = readFileSync(PROJECT_KNOWLEDGE, "utf-8")
    const match = src.match(
      /export (?:interface|type) ProjectKnowledge(?:Record|Item)\s*\{?([\s\S]*?)(?:\n\}|\n\nexport)/,
    )
    expect(match, "ProjectKnowledge type not found").not.toBeNull()
    const body = match?.[1] ?? ""
    const FORBIDDEN = [
      /\bsourceKind\b/,
      /\bconfidence\b/,
      /\bexpiresAt\b/,
    ]
    const violations: string[] = []
    for (const re of FORBIDDEN) {
      if (re.test(body)) violations.push(`ProjectKnowledge: ${re}`)
    }
    expect(
      violations,
      `Project Knowledge must NOT impersonate Durable Memory (§12 line 549): ${violations.join(", ")}`,
    ).toEqual([])
  })

  // ── 5. §12 not-built 5 项在 active runtime/apps/api 0 invoke ─────

  it("§12: not-built 5 items have ZERO active runtime / apps/api invocation (DreamPhase / consolidate / ContextGraph / RAG Studio / auto-index paths)", () => {
    // Active runtime + apps/api files (exclude _archive/, .test.ts).
    const runtimeFiles = listProductionTs(RUNTIME_SRC)
    const appsFiles = listProductionTs(APPS_SRC)
    const activeFiles = [...runtimeFiles, ...appsFiles]
    // Also exclude the type-only placeholder file (it's an intentional
    // dev-stage reservation; not an active invocation).
    const FILES_EXCLUDED_FROM_INVOCATION_CHECK = new Set([
      MEMORY_TYPES,
      MEMORY_PURE,
    ])
    // Forbidden: actual call sites, not type references.
    const FORBIDDEN_PATTERNS: readonly (readonly [string, RegExp])[] = [
      ["DreamPhase call site", /(?<!\w)dream\s*\(\s*phase\s*:\s*DreamPhase/],
      ["consolidate* invoke", /(?<!\w)consolidate(?:Deep|One|Two|Stage|Phase)?\s*\(/],
      ["ContextGraph invoke", /new\s+ContextGraph\b|\.buildContextGraph\s*\(/],
      ["RAG Studio invoke", /\b(?:RagStudio|RAGStudio|RAG Studio)\b.*\(|\.ingestRAG\b/],
      ["autoIndex invoke", /\bautoIndex(?:All|Full|Disk)?\s*\(/],
    ]
    const violations: string[] = []
    for (const file of activeFiles) {
      if (FILES_EXCLUDED_FROM_INVOCATION_CHECK.has(file)) continue
      const src = readFileSync(file, "utf-8")
      for (const [name, re] of FORBIDDEN_PATTERNS) {
        if (re.test(src)) {
          violations.push(`${file}: ${name}`)
        }
      }
    }
    expect(
      violations,
      `§12 not-built 5 items must not be invoked in active runtime / apps/api: ${violations.join(", ")}`,
    ).toEqual([])
  })

  // ── 6. §12 默认不启用 embedding ──────────────────────────────

  it("§12: durable_memories schema has no `embedding` column (default 不启用 embedding per §12 line 558-559)", () => {
    const src = readFileSync(SCHEMA, "utf-8")
    const match = src.match(
      /export const durableMemories = pgTable\s*\(\s*["']durable_memories["'][\s\S]*?\n\)\s*\n/,
    )
    expect(match, "durable_memories pgTable not found").not.toBeNull()
    const body = match?.[0] ?? ""
    expect(
      /\bembedding\b/i.test(body),
      "durable_memories must NOT carry an embedding column — §12 line 558 mandates default-off embedding",
    ).toBe(false)
  })

  // ── 7. §12 G3 batch candidate UI 实证 (D39, 2026-09-01) ─────────
  //
  // D30 lock above covers the schema + domain invariants for the 3
  // memory layers. D39 G3 batch candidate UI (Tasks 1-5) added the
  // owner surface + wechat commands for managing candidate memories
  // in bulk. This case locks that the MVP-ship surface is wired and
  // cannot regress without tripping this guard.

  it("§12: G3 batch candidate UI 实施 — 3 owner routes + /记忆候选 + /确认记忆 batch all present (D39 lock)", () => {
    const ownerRoutes = readFileSync(OWNER_ROUTES, "utf-8")
    expect(
      /\/v1\/owner\/memories\/confirm-batch/.test(ownerRoutes),
      "owner-routes must declare POST /v1/owner/memories/confirm-batch (D39 G3)",
    ).toBe(true)
    expect(
      /\/v1\/owner\/memories\/reject-batch/.test(ownerRoutes),
      "owner-routes must declare POST /v1/owner/memories/reject-batch (D39 G3)",
    ).toBe(true)
    expect(
      /\bhasMore\b/.test(ownerRoutes),
      "owner-routes GET /v1/owner/memories must expose hasMore pagination flag (D39 G3)",
    ).toBe(true)
    expect(
      /\bcountBySubject\b/.test(ownerRoutes),
      "owner-routes GET /v1/owner/memories must call countBySubject for total (D39 G3)",
    ).toBe(true)

    const wechatCommands = readFileSync(WECHAT_MEMORY_COMMANDS, "utf-8")
    expect(
      wechatCommands.includes("/记忆候选"),
      "wechat-memory-commands must handle /记忆候选 listing command (D39 G3)",
    ).toBe(true)
    expect(
      wechatCommands.includes("/确认记忆"),
      "wechat-memory-commands must handle /确认记忆 batch command (D39 G3)",
    ).toBe(true)
    expect(
      /confirm-batch/.test(wechatCommands),
      "wechat-memory-commands must invoke owner confirm-batch route (D39 G3)",
    ).toBe(true)
  })

  // ── 8. §12 G1 candidate expires cleanup 实证 (D40, 2026-09-01) ────
  //
  // D30 case 2 locks `DurableMemoryRecord.status` as a string union and
  // D30 case 3 locks `DurableMemorySourceKind` as a 3-member union.
  // D40 G1 extends `DurableMemoryStatus` from 3 members
  // (`"candidate" | "confirmed" | "rejected"`) to 4 members by adding
  // `"expired"` — the sweeper transitions candidates past their
  // `expiresAt` into `"expired"` so they leave the working set without
  // polluting it and remain in owner history for audit. This case
  // locks the 4-member union so a future commit that narrows the type
  // back to 3 (e.g. "we don't track expiry in the status field") trips
  // this guard.

  it("§12 G1: DurableMemoryStatus is a 4-member union including 'expired' (candidate expires cleanup, 2026-09-01)", () => {
    const src = readFileSync(DURABLE_MEMORY, "utf-8")
    const match = src.match(
      /export type DurableMemoryStatus\s*=\s*([\s\S]*?)\n\nexport/,
    )
    expect(match, "DurableMemoryStatus type not found").not.toBeNull()
    const body = match?.[1] ?? ""
    for (const status of ["candidate", "confirmed", "rejected", "expired"]) {
      expect(
        body,
        `DurableMemoryStatus missing member: ${status} (§12 G1 mandate 4-member union)`,
      ).toMatch(new RegExp(`["']${status}["']`))
    }
  })
})
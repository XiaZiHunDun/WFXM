/**
 * Arch guard (D8-arch-align §20 #11): UI/MCP/浏览器/Schedule 不创建
 * 第二套 Loop 或 Policy，也不能绕过 Ports。
 *
 * Static checks (no runtime):
 *   - `apps/api/src/subagent-worker.ts` imports `runConversationLoop`
 *     from `@butler/runtime/execution` (canonical loop).
 *   - `apps/api/src/subagent-worker.ts` does NOT carry a hand-rolled
 *     LLM-tool loop pattern: `for (... iteration ...)` + `adapter.complete`
 *     with Effect-based timeout would mean a second loop implementation.
 *   - Other entry-point workers in apps/api/ (schedule-worker,
 *     project-knowledge-watch-worker) do not invoke `adapter.complete`
 *     directly — they delegate to `runButlerLoop` / `runConversationLoop`.
 *
 * Runtime behavior is verified by:
 *   - apps/api/src/subagent-worker.test.ts (14 cases covering drains,
 *     tool execution, capability allowlist, audit, slow LLM,
 *     invalid outbox payloads, stop())
 *   - tests/eval/scenarios for main conversation-loop invariants
 */

import { describe, expect, it } from "vitest"
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join, relative } from "node:path"

const SUBAGENT_WORKER = join(__dirname, "../../apps/api/src/subagent-worker.ts")
const SCHEDULE_WORKER = join(__dirname, "../../apps/api/src/schedule-worker.ts")
const MCP_BOOTSTRAP = join(__dirname, "../../apps/api/src/mcp-bootstrap.ts")
const PROJECT_KNOWLEDGE_WATCH = join(
  __dirname,
  "../../apps/api/src/project-knowledge-watch-worker.ts",
)

describe("arch: single LLM-tool loop (§20 #11)", () => {
  it("subagent-worker reuses the canonical conversation loop (no second engine)", () => {
    const src = readFileSync(SUBAGENT_WORKER, "utf-8")
    expect(src).toMatch(/from\s+["']@butler\/runtime\/execution\/index\.js["']/)
    expect(src).toMatch(/\brunConversationLoop\s*\(/)
  })

  it("subagent-worker does NOT carry a hand-rolled LLM-tool loop", () => {
    const src = readFileSync(SUBAGENT_WORKER, "utf-8")
    // Hand-rolled pattern that would indicate a second loop implementation:
    // a for-loop bound + adapter.complete inside. Effect.timeout around
    // adapter.complete in a port is fine — the canonical loop still owns
    // iteration count and timeout enforcement.
    expect(src).not.toMatch(/for\s*\([^)]*iteration[^)]*\)\s*\{[\s\S]*?adapter\.complete/)
  })

  it("schedule-worker delegates LLM execution to runButlerLoop (not a second engine)", () => {
    const src = readFileSync(SCHEDULE_WORKER, "utf-8")
    // schedule-worker calls runScheduleJob which in turn calls runButlerLoop.
    // The schedule-worker itself must not invoke adapter.complete directly.
    expect(src).not.toMatch(/\badapter\.complete\b/)
    expect(src).toMatch(/\brunScheduleJob\s*\(/)
  })

  it("mcp-bootstrap is connection-only (no LLM loop)", () => {
    const src = readFileSync(MCP_BOOTSTRAP, "utf-8")
    expect(src).not.toMatch(/\badapter\.complete\b/)
    expect(src).not.toMatch(/for\s*\([^)]*iteration[^)]*\)/)
  })

  it("project-knowledge-watch-worker is sync-only (no LLM loop)", () => {
    const src = readFileSync(PROJECT_KNOWLEDGE_WATCH, "utf-8")
    expect(src).not.toMatch(/\badapter\.complete\b/)
    expect(src).not.toMatch(/for\s*\([^)]*iteration[^)]*\)/)
  })
})

// ── §15: every LLM call is timeout-bounded ────────────────────────────────

const CONVERSATION_LOOP = join(process.cwd(), "packages/runtime/src/execution/conversation-loop.ts")

function listProductionTs(root: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(root)) {
    if (["node_modules", "dist", "_archive", "coverage"].includes(entry)) continue
    const p = join(root, entry)
    if (statSync(p).isDirectory()) out.push(...listProductionTs(p))
    else if (entry.endsWith(".ts") && !entry.endsWith(".test.ts")) out.push(p)
  }
  return out
}

describe("arch: LLM calls are timeout-bounded (§15)", () => {
  it("canonical loop wraps ports.complete in completeWithTimeout", () => {
    const src = readFileSync(CONVERSATION_LOOP, "utf-8")
    expect(src).toMatch(/completeWithTimeout[\s\S]{0,400}ports\.complete/)
  })

  it("direct adapter.complete call sites are timeout-bounded", () => {
    // Known gap: butler-assembly wraps the Effect adapter into a Promise port
    // for the pi engine, which applies a task-level timeout upstream. Tracked
    // in docs/plans/active/phase2-findings-2026-11-19.md (F-01).
    const KNOWN_UNBOUNDED = new Set(["apps/api/src/butler-assembly.ts"])
    const violations: string[] = []
    const files = [
      ...listProductionTs(join(process.cwd(), "apps")),
      ...listProductionTs(join(process.cwd(), "packages")),
    ]
    for (const file of files) {
      const rel = relative(process.cwd(), file)
      if (KNOWN_UNBOUNDED.has(rel)) continue
      const src = readFileSync(file, "utf-8")
      if (!/\badapter\.complete\s*\(/.test(src)) continue
      const routed = /runConversationLoop\s*\(|completeWithTimeout/.test(src)
      const bounded = /Effect\.timeout/.test(src)
      if (!routed && !bounded) violations.push(rel)
    }
    expect(violations, `unbounded LLM calls: ${violations.join(", ")}`).toEqual([])
  })

  it("adapter implementations do not impose a timeout policy (caller owns it)", () => {
    const violations = listProductionTs(join(process.cwd(), "packages/adapters/src/llm")).filter(
      (f) => /\bEffect\.timeout\b/.test(readFileSync(f, "utf-8")),
    )
    expect(violations).toEqual([])
  })
})

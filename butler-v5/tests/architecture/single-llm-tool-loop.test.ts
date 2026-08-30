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
import { readFileSync } from "node:fs"
import { join } from "node:path"

const SUBAGENT_WORKER = join(
  __dirname,
  "../../apps/api/src/subagent-worker.ts",
)
const SCHEDULE_WORKER = join(
  __dirname,
  "../../apps/api/src/schedule-worker.ts",
)
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
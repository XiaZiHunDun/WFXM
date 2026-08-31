/**
 * Arch guard (D26B-arch-align §20 #6+#13+#15 invariants batch B):
 *
 *   §20 #6 当前状态可直接读取，不依赖全量事件重放
 *   §20 #13 Conversation 无界，Run 有界；同一 Conversation 默认最多一条活动主 Run
 *   §20 #15 工程交接（短 state.md）不是产品能力，禁止映射为 Run、Task 或 Conversation
 *
 * D26B closes the last 3 of §20's 7 un-audited invariants (D25
 * handoff) — combined with D26A's 4 invariants, §20 reaches
 * 15/16 locked + 1/16 design principle (the §18 trigger guard is
 * §20 #12, design-level only).
 *
 * Audit findings (D26B, 2026-08-31):
 *
 *   - #6 — `packages/persistence/src/runtime-store.ts` exposes
 *     `listMessages`, `getRun`, `findActiveMainRun` (current-state
 *     reads from relational tables). The runtime contract
 *     (`packages/domain/src/runtime/store-contract.ts`) declares
 *     these as part of `RuntimeStore`. Event-store reads
 *     (`loadStream`) are audit-only — production paths read
 *     current state directly.
 *
 *   - #13 — `run-engine.ts` is the sole guard site for
 *     "one active main run per conversation": `withConversationLock`
 *     + `findActiveMainRun` + `throw ActiveMainRunConflict` (with
 *     the documented `waiting_external` + trusted-trigger escape
 *     hatch). `wechat-inbound-butler.ts` handles the exception.
 *
 *   - #15 — Persistence schema (`packages/persistence/src/schema.ts`)
 *     and `RuntimeStore` contract do NOT include any "handoff" /
 *     "state.md" / "engineering handoff" / "session checkpoint"
 *     field. The §20 invariant is satisfied by absence — locking
 *     the negative invariant so a future schema addition does not
 *     silently promote handoff files into the product data model.
 *
 * Static checks (no runtime):
 *   - `runtime-store.ts` declares `listMessages` + `getRun` +
 *     `findActiveMainRun` (current-state reads, not event replay).
 *   - `run-engine.ts` uses `withConversationLock` +
 *     `findActiveMainRun` + throws `ActiveMainRunConflict` as the
 *     canonical single-active-main-run guard.
 *   - `ActiveMainRunConflict` class is declared exactly once.
 *   - Entry point (`wechat-inbound-butler.ts`) handles
 *     `ActiveMainRunConflict` (graceful conflict reply).
 *   - Persistence schema + RuntimeStore contract have 0 references
 *     to "handoff" / "state.md" / "session checkpoint" / "state_handoff".
 *
 * Runtime behavior is verified by:
 *   - run-engine.test.ts (single-active-main-run lifecycle + waiting_external escape)
 *   - wechat-inbound-butler.test.ts (ActiveMainRunConflict reply shape)
 *   - runtime-store.test.ts (current-state read paths)
 *
 * Remediation when this guard fires:
 *   - #6 violation (entry point forces event replay to get current state):
 *     §20 #6 §11.1 violation; route the read through the
 *     `RuntimeStore` current-state API instead.
 *   - #13 violation (parallel single-main-run guard):
 *     §20 #13 §4.3 violation; remove the parallel guard and route
 *     the run start through `RunEngine.executeInbound`.
 *   - #15 violation (handoff field appears in schema or contract):
 *     §20 #15 violation; remove the field — engineering handoff is
 *     a process artifact, not a product capability.
 */

import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { join } from "node:path"

const RUNTIME_STORE = join(
  __dirname,
  "../../packages/persistence/src/runtime-store.ts",
)
const STORE_CONTRACT = join(
  __dirname,
  "../../packages/domain/src/runtime/store-contract.ts",
)
const RUN_ENGINE = join(__dirname, "../../packages/runtime/src/run-engine.ts")
const RUN_COORDINATOR = join(
  __dirname,
  "../../packages/runtime/src/run-coordinator.ts",
)
const SCHEMA = join(__dirname, "../../packages/persistence/src/schema.ts")
const WECHAT_INBOUND_BUTLER = join(
  __dirname,
  "../../apps/api/src/wechat-inbound-butler.ts",
)

describe("arch: §20 #6+#13+#15 invariants batch B (D26B)", () => {
  // ── §20 #6: 当前状态可直接读取，不依赖全量事件重放 ──────────

  it("#6: RuntimeStore exposes current-state reads (listMessages + getRun + findActiveMainRun)", () => {
    const src = readFileSync(RUNTIME_STORE, "utf-8")
    expect(
      src).toMatch(/async\s+listMessages\s*\(/)
    expect(src).toMatch(/async\s+getRun\s*\(/)
    expect(src).toMatch(/async\s+findActiveMainRun\s*\(/)
  })

  it("#6: RuntimeStore contract declares current-state API surface", () => {
    const src = readFileSync(STORE_CONTRACT, "utf-8")
    expect(src).toMatch(/readonly\s+listMessages\s*:/)
    expect(src).toMatch(/readonly\s+getRun\s*:/)
    expect(src).toMatch(/readonly\s+findActiveMainRun\s*:/)
  })

  // ── §20 #13: Conversation 无界 Run 有界；同一 Conversation 默认最多一条活动主 Run ──

  it("#13: withConversationLock + findActiveMainRun + ActiveMainRunConflict is the canonical single-active-main-run guard", () => {
    const runEngineSrc = readFileSync(RUN_ENGINE, "utf-8")
    // The guard appears in run-engine's executeInbound (the run start
    // entry point); the ActiveMainRunConflict throw must coexist with
    // findActiveMainRun lookup inside the same withConversationLock.
    expect(runEngineSrc).toMatch(/withConversationLock\s*\(/)
    expect(runEngineSrc).toMatch(/findActiveMainRun\s*\(/)
    expect(runEngineSrc).toMatch(/new\s+ActiveMainRunConflict\s*\(/)
    // The coordinator implements the lock primitive.
    const coordSrc = readFileSync(RUN_COORDINATOR, "utf-8")
    expect(coordSrc).toMatch(
      /withConversationLock\s*<T>\s*\(\s*conversationId/,
    )
  })

  it("#13: ActiveMainRunConflict class is declared exactly once (run-engine.ts)", () => {
    const src = readFileSync(RUN_ENGINE, "utf-8")
    expect(src).toMatch(
      /^export\s+class\s+ActiveMainRunConflict\s+extends\s+Error\b/m,
    )
    // Single declaration; no parallel conflict class elsewhere.
    const declCount = (
      src.match(/^export\s+class\s+ActiveMainRunConflict\b/gm) ?? []
    ).length
    expect(declCount).toBe(1)
  })

  it("#13: wechat-inbound-butler handles ActiveMainRunConflict (graceful conflict reply)", () => {
    const src = readFileSync(WECHAT_INBOUND_BUTLER, "utf-8")
    // The driving adapter must catch the conflict and surface a
    // friendly reply instead of letting it bubble up as a 500.
    expect(src).toMatch(/instanceof\s+ActiveMainRunConflict/)
    // It must also import the exception class.
    expect(src).toMatch(
      /import\s*\{[^}]*\bActiveMainRunConflict\b[^}]*\}\s*from\s*["']@butler\/runtime\/run-engine\.js["']/,
    )
  })

  // ── §20 #15: 工程交接（短 state.md）不是产品能力 ────────────

  it("#15: persistence schema + RuntimeStore contract do NOT reference handoff / state.md / session checkpoint", () => {
    const schemaSrc = readFileSync(SCHEMA, "utf-8")
    const contractSrc = readFileSync(STORE_CONTRACT, "utf-8")
    const FORBIDDEN = [
      /\bhandoff\b/i,
      /\bstate\.md\b/i,
      /\bsession[_-]?checkpoint\b/i,
      /\bstate[_-]?handoff\b/i,
      /\bscratchpad\b/i,
    ]
    const violations: string[] = []
    for (const re of FORBIDDEN) {
      if (re.test(schemaSrc)) violations.push(`schema.ts: ${re}`)
      if (re.test(contractSrc)) violations.push(`store-contract.ts: ${re}`)
    }
    expect(
      violations,
      `handoff / state.md references in schema or RuntimeStore contract: ${violations.join(", ")}`,
    ).toEqual([])
  })
})
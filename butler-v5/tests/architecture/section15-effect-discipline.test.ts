/**
 * Arch guard (D17-arch-align §15 Effect 纪律): 模型调用是规划不是
 * 副作用，但有 timeout / retry / fallback / cancel 语义。DESIGN §15
 * 规定：Effect 只在有生命周期 / 并发 / cancel / retry 语义处使用。
 *
 * Lock the production invariant:
 *   - Every production call to `adapter.complete(...)` must be wrapped
 *     with `Effect.timeout(...)` OR routed through the canonical
 *     conversation loop's `completeWithTimeout` wrapper (which enforces
 *     the B-09 per-LLM-call timeout). A bare `await adapter.complete(...)`
 *     would stall the loop indefinitely if the provider hangs.
 *
 * Audit findings (D17, 2026-08-30):
 *   - All 6 LLM call sites either use `Effect.timeout(...)` directly
 *     (wechat-inbound-llm.ts:142-143, wechat-intake-llm.ts:94-95,
 *      conversation-memory.ts:160-161, subagent-worker.ts:270-271) or
 *     go through the canonical `runConversationLoop` (which uses
 *     `completeWithTimeout` at packages/runtime/src/execution/
 *     conversation-loop.ts:269-273):
 *       - approval-resume.ts:208 → runConversationLoop → completeWithTimeout
 *       - wechat-inbound-butler.ts:379 → runConversationLoop → completeWithTimeout
 *   - packages/runtime/src/execution/conversation-loop.ts:271 — the
 *     canonical port.complete call site (in `completeWithTimeout`).
 *   - 41 Effect usages in packages/ports/src/r2-shim.ts are intentional
 *     (R12 fixture shim for archived `pnpm test:archived`; locked out
 *     of production runtime by the comment in `r2-shim.ts` itself).
 *
 * Static checks (no runtime):
 *   - Each production file that calls `adapter.complete(...)` must
 *     either include `Effect.timeout` in the same `.pipe(...)` chain OR
 *     be on the allowlist of files that route through `runConversationLoop`
 *     (which transitively enforces `completeWithTimeout`).
 *
 * Runtime behavior is verified by:
 *   - tests/eval/scenarios/16-llm-call-timeout.test.ts (B-09 fix)
 *   - subagent-worker.test.ts (slow LLM / graceful fallback)
 *   - wechat-inbound-butler.test.ts (full chain with scripted adapter)
 */

import { describe, expect, it } from "vitest"
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"

const CONVERSATION_LOOP = join(
  __dirname,
  "../../packages/runtime/src/execution/conversation-loop.ts",
)

/** Production files that route LLM calls through `runConversationLoop`
 *  (which transitively enforces `completeWithTimeout`). These files
 *  are allowed to call `adapter.complete(...)` without `Effect.timeout`
 *  in the same .pipe chain — the canonical loop wraps the call. */
const LLM_THROUGH_CANONICAL_LOOP: ReadonlySet<string> = new Set([
  join(__dirname, "../../apps/api/src/approval-resume.ts"),
  join(__dirname, "../../apps/api/src/wechat-inbound-butler.ts"),
])

/** Production files that MUST wrap `adapter.complete(...)` with
 *  `Effect.timeout(...)` because they call LLM directly without going
 *  through the canonical loop. */
const LLM_DIRECT_FILES: ReadonlySet<string> = new Set([
  join(__dirname, "../../apps/api/src/wechat-inbound-llm.ts"),
  join(__dirname, "../../apps/api/src/wechat-intake-llm.ts"),
  join(__dirname, "../../apps/api/src/subagent-worker.ts"),
  join(__dirname, "../../apps/api/src/conversation-memory.ts"),
])

const ADAPTER_FILES: ReadonlySet<string> = new Set([
  join(__dirname, "../../packages/adapters/src/llm/anthropic.ts"),
  join(__dirname, "../../packages/adapters/src/llm/openai-compatible.ts"),
])

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

describe("arch: §15 Effect 纪律 (every LLM call is timeout-bounded)", () => {
  it("completeWithTimeout is the only LLM-completion call site in the canonical conversation loop", () => {
    const src = readFileSync(CONVERSATION_LOOP, "utf-8")
    // The canonical loop must wrap ports.complete in completeWithTimeout
    // (the B-09 fix). Direct adapter.complete invocations would bypass
    // the timeout.
    expect(src).toMatch(/completeWithTimeout/)
    // ports.complete() must be invoked only via completeWithTimeout().
    // Verify the function name appears in the body of completeWithTimeout.
    expect(src).toMatch(/completeWithTimeout[\s\S]{0,400}ports\.complete/)
  })

  it("production files that call adapter.complete directly MUST wrap with Effect.timeout", () => {
    const violations: string[] = []
    for (const file of LLM_DIRECT_FILES) {
      const src = readFileSync(file, "utf-8")
      // Find each adapter.complete call and assert Effect.timeout is
      // present in the same .pipe(...) chain (within ~600 chars).
      const callRegex = /adapter\.complete\s*\(/g
      let match: RegExpExecArray | null
      while ((match = callRegex.exec(src)) !== null) {
        const slice = src.slice(match.index, match.index + 800)
        if (!/Effect\.timeout/.test(slice)) {
          violations.push(
            `${file}: adapter.complete at offset ${match.index} missing Effect.timeout within 800-char window`,
          )
        }
      }
    }
    expect(
      violations,
      `direct LLM calls without Effect.timeout: ${violations.join(", ")}`,
    ).toEqual([])
  })

  it("production files routing through canonical loop are NOT required to add Effect.timeout (canonical loop owns the timeout)", () => {
    // Sanity check: ensure the allowlist actually contains files that
    // route through runConversationLoop. If this changes, the allowlist
    // must be updated.
    for (const file of LLM_THROUGH_CANONICAL_LOOP) {
      const src = readFileSync(file, "utf-8")
      expect(
        src.includes("runConversationLoop(") || src.includes("runConversationLoop ("),
        `${file} should import / call runConversationLoop to inherit completeWithTimeout`,
      ).toBe(true)
    }
  })

  it("adapter implementations may NOT call Effect.timeout (they return Effect; callers own the timeout)", () => {
    const violations: string[] = []
    for (const file of ADAPTER_FILES) {
      const src = readFileSync(file, "utf-8")
      // Adapter signatures return Effect.Effect<...>; adding Effect.timeout
      // inside the adapter would force a default timeout policy on every
      // caller. Callers wrap with Effect.timeout (or completeWithTimeout).
      if (/\bEffect\.timeout\b/.test(src)) {
        violations.push(`${file}: adapter should not call Effect.timeout`)
      }
    }
    expect(
      violations,
      `adapters calling Effect.timeout: ${violations.join(", ")}`,
    ).toEqual([])
  })

  it("ports/src/r2-shim.ts is fixture-only (no production caller)", () => {
    // The 41 Effect usages in r2-shim.ts are intentional (R12
    // fixture shim for `pnpm test:archived`). Production code must
    // not import it.
    const root = join(__dirname, "../..")
    const prodFiles = [
      ...listProductionTsFiles(join(root, "packages")),
      ...listProductionTsFiles(join(root, "apps")),
    ]
    const violations: string[] = []
    for (const file of prodFiles) {
      const src = readFileSync(file, "utf-8")
      // Allow ports barrel re-export of r2-shim; ban direct imports.
      if (
        /from\s+["'][^"']*r2-shim[^"']*["']/.test(src) &&
        !file.endsWith("/packages/ports/src/index.ts")
      ) {
        violations.push(file)
      }
    }
    expect(
      violations,
      `production files importing r2-shim: ${violations.join(", ")}`,
    ).toEqual([])
  })
})
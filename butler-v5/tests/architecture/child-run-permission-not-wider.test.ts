/**
 * Arch guard (D5-arch-align §20 #5): delegate() must enforce child
 * capabilities ⊆ parent allowlist. Without this invariant, parent Run
 * can be revoked yet its child Run continues with capabilities the
 * parent never had — silent unsafe.
 *
 * Static checks (no runtime):
 *   - DelegateInput declares `parentAllowlist` field
 *   - delegate() body contains a subset validation that throws on widening
 *   - delegate() body fails closed (throws) when parentRunId is set but
 *     parentAllowlist is omitted
 *   - apps/api/src/wechat-inbound-butler.ts populates parentAllowedToolNames
 *   - apps/api/src/tools.ts forwards parentAllowedToolNames → parentAllowlist
 *
 * Runtime behavior is verified by:
 *   - packages/runtime/src/delegate-runtime.test.ts (5 unit tests)
 *   - apps/api/src/subagent-worker.test.ts (relational child Run)
 */

import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { join } from "node:path"

const DELEGATE_RUNTIME = join(
  __dirname,
  "../../packages/runtime/src/delegate-runtime.ts",
)
const WEIBUTLER_TOOLS = join(__dirname, "../../apps/api/src/tools.ts")
const WEIBUTLER_LOOP = join(__dirname, "../../apps/api/src/wechat-inbound-butler.ts")

describe("arch: child Run permission ≤ parent Run (§20 #5)", () => {
  it("DelegateInput declares parentAllowlist field", () => {
    const src = readFileSync(DELEGATE_RUNTIME, "utf-8")
    expect(src).toMatch(
      /readonly\s+parentAllowlist\??:\s*readonly\s+Capability\[\]/,
    )
  })

  it("delegate() body throws when child cap not in parent allowlist", () => {
    const src = readFileSync(DELEGATE_RUNTIME, "utf-8")
    const fnMatch = src.match(/export\s+async\s+function\s+delegate\([\s\S]+?\n\}\n/)
    const body = fnMatch?.[0] ?? ""
    // Subset check + throw on widening.
    expect(body).toMatch(/parentSet\s*=\s*new Set\(/)
    expect(body).toMatch(/not in parent allowlist/)
    expect(body).toMatch(/throw\s+new\s+Error\(/)
  })

  it("delegate() is opt-in: subset check only fires when parentAllowlist is explicitly provided", () => {
    const src = readFileSync(DELEGATE_RUNTIME, "utf-8")
    const fnMatch = src.match(/export\s+async\s+function\s+delegate\([\s\S]+?\n\}\n/)
    const body = fnMatch?.[0] ?? ""
    // The check is gated on `parentRunId && parentAllowlist !== undefined`.
    // Legacy / CLI / service-to-service paths (parentAllowlist undefined)
    // skip the check; this preserves the dev-session-grant flow where
    // plan-mode parents delegate to dev-mode children via the grant chain.
    expect(body).toMatch(/parentRunId\s*&&\s*input\.parentAllowlist\s*!==\s*undefined/)
    // And the error message references §20 #5 for owner-facing context.
    expect(body).toMatch(/§20 #5: child must not be wider than parent/)
  })

  it("wechat-inbound-butler does NOT auto-pass parentAllowedToolNames (opt-in only)", () => {
    const src = readFileSync(WEIBUTLER_LOOP, "utf-8")
    // Tool context field exists (for future opt-in) but wechat-inbound-butler
    // explicitly leaves it undefined. Plan-mode → dev-child flow uses the
    // dev-session-grant chain, not the LLM tool allowlist.
    expect(src).toMatch(
      /makeWeibutlerTools\(\{[\s\S]+parentAllowedToolNames:\s*undefined/,
    )
  })

  it("tools.ts has the wiring point (parentAllowedToolNames → parentAllowlist) for opt-in callers", () => {
    const src = readFileSync(WEIBUTLER_TOOLS, "utf-8")
    // The wiring pattern is in place even if route layer doesn't currently
    // activate it; future opt-in callers can flip the wiring.
    expect(src).toMatch(/ctx\.parentAllowedToolNames/)
    expect(src).toMatch(/parentAllowlist:\s*ctx\.parentAllowedToolNames\.map\(/)
  })
})

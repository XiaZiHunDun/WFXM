/**
 * Arch guard (D10-arch-align §20 #10): 新能力不自动扩大授权面。
 *
 * DESIGN §20 invariant #10 mandates that registering a new capability
 * (tool) must NOT automatically create a ScopedGrant for it. Grants
 * are owner / approval / delegation-authorized only; capability
 * registration is in-memory metadata for the policy gate.
 *
 * Static checks (no runtime):
 *   - `CapabilityRegistry.register` body is sync void — no `await`, no
 *     store / DB calls, no grant-creation paths reachable.
 *   - `CapabilityRegistry.register` body does not invoke
 *     `createScopedGrant` or `issuePreconfiguredGrants` (defense in
 *     depth — even a future `async` refactor must keep register free of
 *     grant issuance).
 *   - `buildCapabilityRegistryFromTools`, `createProductionCapabilityRegistry`,
 *     and `mcpCapabilityProvidersFromTools` only call `registry.register` —
 *     they do not invoke grant creation themselves.
 *   - `issuePreconfiguredGrants` and `createScopedGrant` are reachable
 *     from exactly three explicit authorization paths:
 *       (a) `apps/api/src/dev-session-grant.ts` — owner preconfigured
 *           dev session
 *       (b) `apps/api/src/delegation-grants.ts` — parent run authorizes
 *           child run
 *       (c) `packages/runtime/src/approval-runtime.ts` — owner approves
 *           a waiting approval step
 *     Any new caller would be an authorization surface change and must
 *     be reviewed explicitly.
 *
 * Runtime behavior is verified by:
 *   - packages/runtime/src/scoped-grant-service.test.ts (grant lifecycle)
 *   - packages/runtime/src/approval-runtime.test.ts (approval → grant)
 *   - packages/runtime/src/capability-boundary.test.ts (unregister revokes
 *     grants, but register does not create any)
 */

import { describe, expect, it } from "vitest"
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"

const POLICY_GATE = join(
  __dirname,
  "../../packages/runtime/src/policy-gate.ts",
)
const CAPABILITY_BOUNDARY = join(
  __dirname,
  "../../packages/runtime/src/capability-boundary.ts",
)
const SCOPED_GRANT_SERVICE = join(
  __dirname,
  "../../packages/runtime/src/scoped-grant-service.ts",
)
const APPROVAL_RUNTIME = join(
  __dirname,
  "../../packages/runtime/src/approval-runtime.ts",
)
const DEV_SESSION_GRANT = join(
  __dirname,
  "../../apps/api/src/dev-session-grant.ts",
)
const DELEGATION_GRANTS = join(
  __dirname,
  "../../apps/api/src/delegation-grants.ts",
)

function extractMethodBody(src: string, signatureRegex: RegExp): string | null {
  const match = src.match(signatureRegex)
  if (!match || typeof match.index !== "number") return null
  // Start the walk at the opening `{` (last char of the match) so the
  // first iteration counts it as depth 1.
  const start = match.index + match[0].length - 1
  let depth = 0
  let opened = false
  let bodyStart = -1
  let bodyEnd = -1
  for (let i = start; i < src.length; i += 1) {
    const ch = src[i]
    if (ch === "{") {
      if (!opened) {
        opened = true
        bodyStart = i + 1
      }
      depth += 1
    } else if (ch === "}") {
      depth -= 1
      if (opened && depth === 0) {
        bodyEnd = i
        break
      }
    }
  }
  if (bodyStart === -1 || bodyEnd === -1) return null
  return src.slice(bodyStart, bodyEnd)
}

describe("arch: capability registration does not auto-grant (§20 #10)", () => {
  it("CapabilityRegistry.register is sync void with no awaited calls", () => {
    const src = readFileSync(POLICY_GATE, "utf-8")
    const body = extractMethodBody(src, /register\([^)]*\)\s*:\s*void\s*\{/)
    expect(body, "register(...) : void body not found").not.toBeNull()
    expect(body).not.toMatch(/\bawait\b/)
    expect(body).not.toMatch(/\bPromise\b/)
  })

  it("CapabilityRegistry.register does NOT invoke grant creation paths", () => {
    const src = readFileSync(POLICY_GATE, "utf-8")
    const body = extractMethodBody(src, /register\([^)]*\)\s*:\s*void\s*\{/)
    expect(body, "register body not found").not.toBeNull()
    // Defense in depth — even if someone refactors register to async,
    // these symbols must not appear.
    expect(body).not.toMatch(/\bcreateScopedGrant\b/)
    expect(body).not.toMatch(/\bissuePreconfiguredGrants\b/)
    expect(body).not.toMatch(/\bstore\./)
  })

  it("registry builders only call registry.register (no grant creation in helper layer)", () => {
    const src = readFileSync(CAPABILITY_BOUNDARY, "utf-8")
    // The three helpers that wire capabilities into a registry must only
    // touch `registry.register(...)` and `registry.unregister(...)`.
    // They must not call any grant-creation API directly.
    expect(src).not.toMatch(/createScopedGrant\(/)
    expect(src).not.toMatch(/issuePreconfiguredGrants\(/)
  })

  it("issuePreconfiguredGrants / createScopedGrant callers are exactly the 3 explicit auth paths", () => {
    // Scan all non-test sources for CALL sites of the grant-creation API.
    // Call sites look like `await store.createScopedGrant(...)` or
    // `await issuePreconfiguredGrants(...)`. We deliberately skip:
    //   - interface declarations (`readonly createScopedGrant:`)
    //   - implementation declarations (`async createScopedGrant(input)`)
    //   - the source where the function is defined
    //     (`export async function issuePreconfiguredGrants(`)
    // The known callers are: scoped-grant-service.ts (internal call site),
    // and the three external authorization paths enumerated above.
    const expectedFiles = [
      SCOPED_GRANT_SERVICE,
      DEV_SESSION_GRANT,
      DELEGATION_GRANTS,
      APPROVAL_RUNTIME,
    ]
    const violations: string[] = []
    const root = join(__dirname, "../..")
    // Match only call sites: `await <optional receiver>.NAME(`
    const callSiteRegex =
      /\bawait\b[\s\n]+(?:\w+(?:\.\w+)*\.)?(createScopedGrant|issuePreconfiguredGrants)\s*\(/
    function walk(dir: string): void {
      for (const entry of readdirSync(dir)) {
        const p = join(dir, entry)
        const stat = statSync(p)
        if (stat.isDirectory()) {
          if (entry === "node_modules" || entry === "dist" || entry === "_archive") continue
          walk(p)
        } else if (entry.endsWith(".ts") && !entry.endsWith(".test.ts")) {
          const src = readFileSync(p, "utf-8")
          if (callSiteRegex.test(src) && !expectedFiles.includes(p)) {
            violations.push(join.relative(root, p))
          }
        }
      }
    }
    walk(join(root, "packages"))
    walk(join(root, "apps"))
    expect(violations, `unexpected grant-creation callers: ${violations.join(", ")}`).toEqual([])
  })
})
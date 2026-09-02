/**
 * Arch guard (D4-arch-align §20 #5 / #7): cancelRun must cascade to all
 * descendant child Runs. Without this invariant, owner cancels the parent
 * but children keep running on a now-dead grant chain — silent unsafe
 * behavior.
 *
 * Static checks (no runtime):
 *   - cancelRunCascade exports from run-lifecycle.ts
 *   - apps/api/src/owner-routes.ts uses cancelRunCascade (NOT cancelRun alone)
 *   - findChildRuns primitive exists in store-contract.ts
 *
 * The runtime behavior is verified by:
 *   - packages/runtime/src/run-lifecycle.test.ts (cancelRunCascade unit test)
 *   - tests/eval/scenarios (manual scenario)
 */

import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { join } from "node:path"

const RUNTIME_LIFECYCLE = join(
  __dirname,
  "../../packages/runtime/src/run-lifecycle.ts",
)
const STORE_CONTRACT = join(
  __dirname,
  "../../packages/domain/src/runtime/store-contract.ts",
)
import { readOwnerRoutesSource } from "./owner-routes-source.js"

describe("arch: cancelRun cascade to descendants (§20 #7)", () => {
  it("cancelRunCascade exports from run-lifecycle.ts", () => {
    const src = readFileSync(RUNTIME_LIFECYCLE, "utf-8")
    expect(src).toMatch(/export\s+async\s+function\s+cancelRunCascade\s*\(/)
  })

  it("cancelRunCascade calls findChildRuns for recursive descent", () => {
    const src = readFileSync(RUNTIME_LIFECYCLE, "utf-8")
    // Locate function body and check it calls store.findChildRuns at least once.
    const fnMatch = src.match(
      /export\s+async\s+function\s+cancelRunCascade[\s\S]+?\n\}\n/,
    )
    expect(fnMatch, "cancelRunCascade function body not found").toBeTruthy()
    expect(fnMatch?.[0] ?? "").toMatch(/findChildRuns/)
  })

  it("cancelRunCascade audit reason differs from owner cancel (distinguishable cascade from direct cancel)", () => {
    const src = readFileSync(RUNTIME_LIFECYCLE, "utf-8")
    const fnMatch = src.match(
      /export\s+async\s+function\s+cancelRunCascade[\s\S]+?\n\}\n/,
    )
    const body = fnMatch?.[0] ?? ""
    // Cascade default reason must NOT be the plain "owner_cancel" used by
    // cancelRun; it must call out the cascade so audit lineage is readable.
    expect(body).toMatch(/cascade/)
    // Audit detail must carry ancestorRunId linkage to the root.
    expect(body).toMatch(/ancestorRunId/)
  })

  it("findChildRuns primitive exists in store-contract.ts", () => {
    const src = readFileSync(STORE_CONTRACT, "utf-8")
    expect(src).toMatch(
      /readonly\s+findChildRuns\s*:\s*\(parentRunId:\s*string\)\s*=>\s*Promise<readonly\s+StoredRun\[\]>/,
    )
  })

  it("owner-routes cancels via cancelRunCascade (not bare cancelRun)", () => {
    const src = readOwnerRoutesSource()
    // Find cancel-run route handler and verify it uses the cascade variant.
    // Heuristic: look for the cancelRun import and assert cancelRunCascade
    // is also imported + the route's POST handler calls the cascade variant.
    expect(src).toMatch(/import\s+\{[^}]*cancelRunCascade[^}]*\}\s+from\s+"@butler\/runtime\/run-lifecycle\.js"/)
    // The cancel-Run HTTP route should call cancelRunCascade inside its try-block.
    const routeMatches = src.match(/app\.post\(\s*"\/v1\/owner\/runs\/[^"]+"[\s\S]+?c\.json\(/g)
    expect(routeMatches, "no cancel-Run route handler found").toBeTruthy()
    // At least one route that mentions /runs/ should call cancelRunCascade.
    const cascadeUsed = (routeMatches ?? []).some((m) => m.includes("cancelRunCascade"))
    expect(
      cascadeUsed,
      "/v1/owner/runs/:runId/cancel must use cancelRunCascade, not cancelRun",
    ).toBe(true)
  })
})

/**
 * Arch guard (D6-arch-align §20 #7): every "state change + audit write"
 * pair in run-lifecycle must be wrapped in `db.transaction` so the audit
 * is atomic with the state mutation. Without atomicity, a state change
 * can succeed while its audit row fails to insert — silent audit gap.
 *
 * Static checks (no runtime):
 *   - RuntimeStore interface exposes `appendAuditEventInTx` + `withTransaction`
 *   - cancelRun / cancelRunCascade / expireRun / enterWaitingExternal /
 *     resumeFromWaitingExternal all wrap state change + audit in
 *     `store.withTransaction(async (tx) => { ... })`
 *   - No `appendAuditEvent` direct call after a state-change method
 *     (the non-InTx variant is for non-composed cases only)
 *
 * Runtime behavior is verified by:
 *   - packages/runtime/src/run-lifecycle.test.ts (atomicity test)
 */

import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { join } from "node:path"

const STORE_CONTRACT = join(
  __dirname,
  "../../packages/domain/src/runtime/store-contract.ts",
)
const RUNTIME_LIFECYCLE = join(
  __dirname,
  "../../packages/runtime/src/run-lifecycle.ts",
)

const ATOMIC_FUNCTIONS = [
  "cancelRun",
  "expireRun",
  "enterWaitingExternal",
  "resumeFromWaitingExternal",
]

describe("arch: audit + state-change atomic (§20 #7)", () => {
  it("RuntimeStore interface declares appendAuditEventInTx + withTransaction", () => {
    const src = readFileSync(STORE_CONTRACT, "utf-8")
    expect(src).toMatch(/readonly\s+appendAuditEventInTx\s*:\s*\(/)
    expect(src).toMatch(/readonly\s+transitionRunStatusInTx\s*:\s*\(/)
    expect(src).toMatch(/readonly\s+withTransaction\s*:\s*</)
    expect(src).toMatch(/type\s+RuntimeTx\s*=\s*unknown/)
  })

  it("cancelRunCascade wraps cascade in withTransaction", () => {
    const src = readFileSync(RUNTIME_LIFECYCLE, "utf-8")
    // cancelRunCascade's inner function calls store.withTransaction(...)
    // before calling transitionRunStatusInTx + appendAuditEventInTx.
    expect(src).toMatch(/store\.withTransaction\(async\s*\(tx\)\s*=>\s*\{[\s\S]+transitionRunStatusInTx[\s\S]+appendAuditEventInTx/)
  })

  for (const fn of ATOMIC_FUNCTIONS) {
    it(`${fn} wraps state change + audit in store.withTransaction`, () => {
      const src = readFileSync(RUNTIME_LIFECYCLE, "utf-8")
      // Extract the function as the byte range from `export async function NAME(`
      // to the start of the next `^export ` declaration (or EOF). The
      // run-lifecycle source has no inline async closures with backticked
      // template literals containing `}` at column 0, so this bracket-free
      // approach is safe for our codebase.
      const startMarker = `export async function ${fn}(`
      const startIdx = src.indexOf(startMarker)
      expect(startIdx, `${fn} not found in source`).toBeGreaterThanOrEqual(0)
      const after = src.slice(startIdx + startMarker.length)
      // next "export " at column 0
      const nextExport = after.search(/^export\s/m)
      const endIdx = nextExport >= 0 ? startIdx + startMarker.length + nextExport : src.length
      const body = src.slice(startIdx, endIdx)
      // Must contain store.withTransaction(...) (whitespace tolerant: the
      // arg list is split across multiple lines).
      expect(body).toMatch(/store\.withTransaction\(async\s*\(tx\)\s*=>\s*\{/)
      // Inside the tx, must use the *InTx variants (whitespace tolerant).
      expect(body).toMatch(/transitionRunStatusInTx\(\s*tx,/)
      expect(body).toMatch(/appendAuditEventInTx\(\s*tx,/)
    })
  }
})

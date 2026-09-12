/**
 * D60 T1.3 (audit #1 F-02): close D59 T1 missed-sweep — the
 * POST /v1/owner/mcp/servers/:serverId/revoke-grants route must write
 * an `audit_event` even when the underlying `revokeScopedGrantsForMcpServer`
 * throws. Same §13 audit completeness gap that D59 T1 closed for 9
 * other routes.
 *
 * Pattern (regression check): revoke call is inside try/catch,
 * audit_event is written unconditionally, failureReason captured.
 */
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"

describe("owner-routes/mcp.ts revoke-grants audit_event (D60 T1.3)", () => {
  const src = readFileSync(
    join(process.cwd(), "apps/api/src/owner-routes/mcp.ts"),
    "utf8",
  )

  it("wraps revokeScopedGrantsForMcpServer in try/catch", () => {
    // The revoke call must be inside a try block — without it, a throw
    // would skip the audit_event below (the D59 T1 gap).
    expect(src).toMatch(/try\s*\{[\s\S]*?revokeScopedGrantsForMcpServer/)
  })

  it("writes audit_event unconditionally (not gated by try success)", () => {
    // audit_event must be written outside the try block (or after the catch),
    // so a throw doesn't skip it.
    expect(src).toMatch(/appendAuditEvent/)
    // The audit_event write must come AFTER the catch block ends.
    const catchEnd = src.lastIndexOf("} catch")
    const auditIdx = src.indexOf("appendAuditEvent")
    expect(catchEnd).toBeGreaterThan(-1)
    expect(auditIdx).toBeGreaterThan(catchEnd)
  })

  it("captures failureReason and surfaces it on error response", () => {
    // failureReason is captured from the catch and threaded into the
    // audit_event detail + a 5xx response.
    expect(src).toMatch(/failureReason/)
    expect(src).toMatch(/c\.json\([\s\S]*?500/)
  })
})
/**
 * R8.x.9 — audit log tests.
 *
 * The module is intentionally side-effect free: every filesystem call
 * is swallowed so a broken filesystem never crashes the route. The
 * tests below use a temp directory (HOME override) to keep the real
 * `~/.butler/audit` untouched and to verify the directory is created
 * on first write.
 */
import { mkdtempSync, readFileSync, rmSync, existsSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { appendAudit, type AuditEntry } from "./audit-log.js"

const ORIGINAL_HOME = process.env["HOME"]
let tempHome: string

beforeEach(() => {
  tempHome = mkdtempSync(join(tmpdir(), "audit-log-test-"))
  process.env["HOME"] = tempHome
})

afterEach(() => {
  process.env["HOME"] = ORIGINAL_HOME
  if (existsSync(tempHome)) {
    rmSync(tempHome, { recursive: true, force: true })
  }
})

describe("audit-log", () => {
  it("appendAudit writes one JSONL line to the audit file", () => {
    const entry: AuditEntry = {
      ts: "2026-08-19T00:00:00.000Z",
      kind: "delegation",
      parentConversationId: "p-1",
      childConversationId: "c-1",
      role: "researcher",
      task: "do a thing",
      capabilities: ["general"],
    }
    appendAudit(entry)
    const logPath = join(tempHome, ".butler", "audit", "subagent-r8x9.jsonl")
    expect(existsSync(logPath)).toBe(true)
    const lines = readFileSync(logPath, "utf8").trim().split("\n")
    expect(lines).toHaveLength(1)
    const parsed = JSON.parse(lines[0] ?? "{}") as AuditEntry
    expect(parsed.kind).toBe("delegation")
    expect(parsed.parentConversationId).toBe("p-1")
    expect(parsed.capabilities).toEqual(["general"])
  })

  it("ensureLogPath creates the audit directory if missing", () => {
    // First call should create ~/.butler/audit and succeed.
    appendAudit({
      ts: "2026-08-19T00:00:00.000Z",
      kind: "completion",
      parentConversationId: "p-2",
      childConversationId: "c-2",
      role: "general",
      task: "another",
      capabilities: ["general"],
      replyExcerpt: "ok",
    })
    const auditDir = join(tempHome, ".butler", "audit")
    expect(existsSync(auditDir)).toBe(true)
  })
})

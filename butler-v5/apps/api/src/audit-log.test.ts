/**
 * R8.x.9 — audit log tests.
 *
 * The module is intentionally side-effect free: every filesystem call
 * is swallowed so a broken filesystem never crashes the route. The
 * tests below use a temp directory (HOME override) to keep the real
 * audit path untouched and to verify the directory is created on first write.
 */
import { mkdtempSync, readFileSync, rmSync, existsSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { appendAudit, readRecentSubagentAudit, resolveSubagentAuditLogPath, type AuditEntry } from "./audit-log.js"

const ORIGINAL_HOME = process.env["HOME"]
const ORIGINAL_AUDIT_PATH = process.env["BUTLER_V5_SUBAGENT_AUDIT_PATH"]
let tempHome: string

beforeEach(() => {
  tempHome = mkdtempSync(join(tmpdir(), "audit-log-test-"))
  process.env["HOME"] = tempHome
  delete process.env["BUTLER_V5_SUBAGENT_AUDIT_PATH"]
})

afterEach(() => {
  process.env["HOME"] = ORIGINAL_HOME
  if (ORIGINAL_AUDIT_PATH === undefined) {
    delete process.env["BUTLER_V5_SUBAGENT_AUDIT_PATH"]
  } else {
    process.env["BUTLER_V5_SUBAGENT_AUDIT_PATH"] = ORIGINAL_AUDIT_PATH
  }
  if (existsSync(tempHome)) {
    rmSync(tempHome, { recursive: true, force: true })
  }
})

describe("audit-log", () => {
  it("defaults audit path under ~/.config/butler-v5/audit/", () => {
    expect(resolveSubagentAuditLogPath(process.env)).toBe(
      join(tempHome, ".config", "butler-v5", "audit", "subagent.jsonl"),
    )
  })

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
    const logPath = join(tempHome, ".config", "butler-v5", "audit", "subagent.jsonl")
    expect(existsSync(logPath)).toBe(true)
    const lines = readFileSync(logPath, "utf8").trim().split("\n")
    expect(lines).toHaveLength(1)
    const parsed = JSON.parse(lines[0] ?? "{}") as AuditEntry
    expect(parsed.kind).toBe("delegation")
    expect(parsed.parentConversationId).toBe("p-1")
    expect(parsed.capabilities).toEqual(["general"])
  })

  it("ensureLogPath creates the audit directory if missing", () => {
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
    const auditDir = join(tempHome, ".config", "butler-v5", "audit")
    expect(existsSync(auditDir)).toBe(true)
  })

  it("readRecentSubagentAudit returns newest rows", () => {
    appendAudit({
      ts: "2026-08-19T00:00:00.000Z",
      kind: "delegation",
      parentConversationId: "p-a",
      childConversationId: "c-a",
      role: "general",
      task: "first",
      capabilities: ["general"],
    })
    appendAudit({
      ts: "2026-08-19T00:00:01.000Z",
      kind: "completion",
      parentConversationId: "p-a",
      childConversationId: "c-a",
      role: "general",
      task: "first",
      capabilities: ["general"],
      replyExcerpt: "done",
    })
    const rows = readRecentSubagentAudit(5, process.env)
    expect(rows).toHaveLength(2)
    expect(rows[1]?.kind).toBe("completion")
  })

  it("honors BUTLER_V5_SUBAGENT_AUDIT_PATH override", () => {
    const customPath = join(tempHome, "custom-audit.jsonl")
    process.env["BUTLER_V5_SUBAGENT_AUDIT_PATH"] = customPath
    appendAudit({
      ts: "2026-08-19T00:00:00.000Z",
      kind: "rejection",
      parentConversationId: "p-3",
      childConversationId: "c-3",
      role: "general",
      task: "blocked",
      capabilities: ["general"],
      reason: "policy",
    })
    expect(existsSync(customPath)).toBe(true)
  })
})

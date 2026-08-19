/**
 * R8.x.9 — subagent audit log.
 *
 * Appends one JSON line per delegation / completion / rejection to
 * `~/.butler/audit/subagent-r8x9.jsonl`. Designed for the owner to
 * grep / tail / pipe to a SIEM later; not a structured query log.
 *
 * Constraints:
 *   - Never throws: every filesystem call is wrapped in try/catch so a
 *     broken filesystem cannot kill the route or the worker.
 *   - No `// ts-prune-ignore-next` annotations.
 *   - Directory is created lazily on first write.
 */
import { appendFileSync, mkdirSync } from "node:fs"
import { dirname, join } from "node:path"
import { homedir } from "node:os"

/**
 * Compute the audit log path lazily so tests can override
 * `process.env.HOME` between calls. Reading `homedir()` at module
 * load would freeze the path to the original $HOME.
 */
function auditLogPath(): string {
  const home = process.env["HOME"] ?? homedir()
  return join(home, ".butler", "audit", "subagent-r8x9.jsonl")
}

function ensureLogPath(): void {
  try {
    mkdirSync(dirname(auditLogPath()), { recursive: true })
  } catch {
    // swallow — we never want a broken filesystem to crash the route.
  }
}

/** One audit row written to the JSONL log. */
export interface AuditEntry {
  readonly ts: string
  readonly kind: "delegation" | "completion" | "rejection" | "tool_call"
  readonly parentConversationId: string
  readonly childConversationId: string
  readonly role: string
  readonly task: string
  readonly capabilities: readonly string[]
  readonly replyExcerpt?: string
  readonly reason?: string
  readonly toolName?: string
}

/**
 * Append one audit row. Failures are intentionally swallowed so the
 * caller (route or worker) never has to defend against audit-log IO.
 */
export function appendAudit(entry: AuditEntry): void {
  ensureLogPath()
  try {
    appendFileSync(auditLogPath(), JSON.stringify(entry) + "\n")
  } catch {
    // swallow
  }
}

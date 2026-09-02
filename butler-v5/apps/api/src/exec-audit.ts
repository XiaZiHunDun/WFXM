/**
 * D47 — exec/subprocess/tool behavior audit accounting (S6 apps/api).
 *
 * Every subprocess execution at the S6 exec anchors (workspace-tools,
 * mcp-spawn, wechat-quality-gate, dev-quality-gate) appends one
 * `exec.executed` audit event (cmd / cwd / exit / durationMs / outcome)
 * into the existing RuntimeStore audit pipeline.
 *
 * Compliance:
 *   - Observation/audit only — never issues a permission, never opens a
 *     new side-effect path.
 *   - Never throws and never blocks the exec path: if no store is wired
 *     (e.g. tests) or the append fails, the execution is unaffected.
 */
import type { RuntimeStore } from "@butler/domain/runtime.js"

/** Runtime-injected audit context carried into exec points (from wiring). */
export interface ExecAuditContext {
  readonly runtimeStore?: RuntimeStore
  readonly conversationId?: string | null
  readonly runId?: string | null
  /** Who triggered the execution (owner id / role / server id). */
  readonly subject?: string
}

export type ExecOutcome = "ok" | "failed" | "spawned"

/** One exec execution audit record — fields aligned with existing audit events. */
export interface ExecAuditRecord {
  readonly cmd: string
  readonly cwd: string
  readonly exit: number | null
  readonly durationMs: number
  readonly outcome: ExecOutcome
  readonly detail?: Readonly<Record<string, unknown>>
}

/**
 * Best-effort `exec.executed` audit append. Awaited at async exec points so
 * the record lands before the exec result resolves (avoids racing a DB
 * teardown, e.g. PGlite wasm close in tests). Swallows all failures so audit
 * can never break the exec path. Safe to call with an undefined context (no
 * store wired → no-op). Callers in genuinely sync contexts (mcp-spawn) should
 * use `void recordExecAudit(...)`.
 */
export async function recordExecAudit(
  ctx: ExecAuditContext | undefined,
  record: ExecAuditRecord,
): Promise<void> {
  const store = ctx?.runtimeStore
  if (!store) return
  try {
    await store.appendAuditEvent({
      auditId: crypto.randomUUID(),
      runId: ctx.runId ?? null,
      conversationId: ctx.conversationId ?? null,
      action: "exec.executed",
      subject: ctx.subject ?? "system",
      detail: {
        kind: "exec",
        cmd: record.cmd,
        cwd: record.cwd,
        exit: record.exit,
        durationMs: record.durationMs,
        outcome: record.outcome,
        ...record.detail,
      },
      createdAt: new Date(),
    })
  } catch {
    // audit must never break the exec path; mock/partial store in tests may
    // not implement appendAuditEvent
  }
}

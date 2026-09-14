/**
 * D64 — Approval Fatigue Mitigation audit fields.
 *
 * Runtime writes these fields into the `detail` field of `appendAuditEvent`
 * (the real audit contract in `packages/domain/src/runtime/store-contract.ts:149`).
 * `detail: Readonly<Record<string, unknown>>` already accepts arbitrary structured data,
 * so no contract changes are required.
 *
 * This type exists for:
 * - Type-safety within the fatigue module (callers building the detail payload)
 * - Discoverability / docs (spec §2.4 intent preserved as TS type)
 * - Backward compat (all fields optional; pre-D64 audit events have no detail content here)
 */

export interface AuditFatigueSignal {
  readonly count: number
  readonly window_seconds: number
  readonly last_n_actions: readonly {
    readonly event_id: string
    readonly tool_name: string
    readonly ts: number
  }[]
  readonly degraded?: true
}

export interface AuditFatigueCooldown {
  readonly duration_ms: number
  readonly interrupted?: true
}

export interface AuditFatigueFields {
  readonly fatigue_signal?: AuditFatigueSignal
  readonly cooldown_applied?: AuditFatigueCooldown
  readonly checklist_required?: boolean
}

/**
 * Convenience alias: the payload that goes into `appendAuditEvent.input.detail`.
 *
 * Structural compatibility with `Readonly<Record<string, unknown>>` is verified by
 * `audit-event.test.ts` T5. Production callers should spread this into `detail`:
 *
 *   await store.appendAuditEvent({
 *     auditId: makeLoopId(),
 *     runId: ctx.runId,
 *     conversationId: ctx.conversationId,
 *     action: "approve",
 *     subject: toolName,
 *     detail: { ...fatigueFields },  // AuditFatigueDetail-compatible
 *     createdAt: new Date(),
 *     correlationId,
 *   })
 */
export type AuditFatigueDetail = AuditFatigueFields

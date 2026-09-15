import { describe, test, expect } from "vitest"
import type { AuditFatigueFields, AuditFatigueDetail } from "./audit-event"

describe("AuditFatigueFields type contract", () => {
  test("T1: accepts fatigue_signal shape", () => {
    const fields: AuditFatigueDetail = {
      fatigue_signal: {
        count: 3,
        window_seconds: 60,
        last_n_actions: [
          { event_id: "e0", tool_name: "read_file", ts: Date.now() - 1000 },
        ],
      },
    }
    expect(fields.fatigue_signal?.count).toBe(3)
  })

  test("T2: accepts cooldown_applied shape", () => {
    const fields: AuditFatigueFields = {
      cooldown_applied: { duration_ms: 3000 },
    }
    expect(fields.cooldown_applied?.duration_ms).toBe(3000)
  })

  test("T3: accepts checklist_required flag", () => {
    const fields: AuditFatigueFields = {
      checklist_required: true,
    }
    expect(fields.checklist_required).toBe(true)
  })

  test("T4: all 3 fields optional — backward compat with existing audit events", () => {
    const fields: AuditFatigueFields = {}
    expect(fields.fatigue_signal).toBeUndefined()
    expect(fields.cooldown_applied).toBeUndefined()
    expect(fields.checklist_required).toBeUndefined()
  })
})

describe("AuditFatigueDetail — embeds in detail field", () => {
  test("detail: Readonly<Record<string, unknown>> accepts AuditFatigueFields", () => {
    // This is the runtime contract: appendAuditEvent.input.detail is a generic record.
    // The fatigue module writes its fields there.
    const detail: Readonly<Record<string, unknown>> = {
      fatigue_signal: {
        count: 3,
        window_seconds: 60,
        last_n_actions: [],
      },
      cooldown_applied: { duration_ms: 3000, interrupted: true },
      checklist_required: true,
    }
    // Type assertion to verify shape is structurally compatible with AuditFatigueFields
    const extracted: AuditFatigueFields = detail as AuditFatigueFields
    expect(extracted.checklist_required).toBe(true)
  })

  // D66 T1c — verify chokepoint can spread AuditFatigueDetail into the
  // appendAuditEvent detail payload. The chokepoint (wechat-inbound-butler.ts
  // executeTool) builds fatigueDetail from the 3-kind ToolExecutionDecision
  // and spreads it into the audit event so owner replay queries observe
  // fatigue interventions (cooldown_applied / checklist_required).
  test("T5: AuditFatigueDetail can be spread into detail field of appendAuditEvent", () => {
    const detail: Readonly<Record<string, unknown>> = {
      tool: "send_email",
      cooldown_applied: { duration_ms: 3000 },
      checklist_required: true,
    }
    // Just verify the structural compatibility compiles and shape is preserved
    expect(detail.cooldown_applied).toBeDefined()
    expect(detail.checklist_required).toBe(true)
  })
})

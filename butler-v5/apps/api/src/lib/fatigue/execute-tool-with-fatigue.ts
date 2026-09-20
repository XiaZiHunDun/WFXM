/**
 * D65 T1 — Extract fatigue decision block from runButlerLoopBody.
 *
 * Pre-condition: inline-approval y/👌 already resolved (D44 1-token preserved).
 *
 * Returns the tool-execution decision after fatigue mitigation:
 * - `allow` → caller executes tool directly
 * - `cooldown` → caller sleeps for durationMs
 * - `checklist` → caller throws RunPauseForApproval with inline-rendered prompt
 *
 * D74 T3 (audit #20 CQ-001): thread `signal` (count + window + last_n_actions)
 * into the decision shape so audit emit at wechat-inbound-butler.ts:573
 * can populate `detail.fatigue_signal` instead of dropping the upstream
 * fatigue telemetry on the floor. 4 cycles of audit carry closed.
 *
 * Exhaustive mapping of PolicyDecision; new actions require coordinated update.
 */
import { evaluateInlineApproval } from "./policy"
import type { AuditLogReader, FatigueSignal } from "./signal"

export type ToolExecutionDecision =
  | { readonly kind: "allow"; readonly signal?: FatigueSignal }
  | { readonly kind: "cooldown"; readonly durationMs: number; readonly signal: FatigueSignal }
  | { readonly kind: "checklist"; readonly items: readonly string[]; readonly signal: FatigueSignal }

export async function executeToolWithFatigue(
  toolName: string,
  toolArgs: Readonly<Record<string, unknown>>,
  reader: AuditLogReader,
): Promise<ToolExecutionDecision> {
  const decision = await evaluateInlineApproval({ tool_name: toolName, args: toolArgs }, reader)
  switch (decision.action) {
    case "allow":
      return { kind: "allow" }
    case "cooldown":
      return { kind: "cooldown", durationMs: decision.duration_ms, signal: decision.signal }
    case "checklist":
      return { kind: "checklist", items: decision.items, signal: decision.signal }
    default:
      throw new Error(`unhandled PolicyDecision action: ${(decision as { action: string }).action}`)
  }
}

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
 * Exhaustive mapping of PolicyDecision; new actions require coordinated update.
 */
import { evaluateInlineApproval } from "./policy"
import type { AuditLogReader } from "./signal"

export type ToolExecutionDecision =
  | { readonly kind: "allow" }
  | { readonly kind: "cooldown"; readonly durationMs: number }
  | { readonly kind: "checklist"; readonly items: readonly string[] }

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
      return { kind: "cooldown", durationMs: decision.duration_ms }
    case "checklist":
      return { kind: "checklist", items: decision.items }
    default:
      throw new Error(`unhandled PolicyDecision action: ${(decision as { action: string }).action}`)
  }
}

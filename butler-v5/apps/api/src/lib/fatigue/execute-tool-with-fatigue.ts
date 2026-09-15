/**
 * D65 T1 — Extract fatigue decision block from runButlerLoopBody.
 *
 * Pre-condition: inline-approval y/👌 already resolved (D44 1-token preserved).
 *
 * Returns the tool-execution decision after fatigue mitigation:
 * - `allow` → execute tool directly
 * - `cooldown` → render wait prompt + sleep durationMs (caller handles sleep)
 * - `checklist` → throw RunPauseForApproval with rendered prompt (caller handles)
 */
import { evaluateInlineApproval } from "./policy"
import type { ChannelContext } from "./inline-approval-wiring"
import type { AuditLogReader } from "./signal"

export type ToolExecutionDecision =
  | { readonly kind: "allow" }
  | { readonly kind: "cooldown"; readonly durationMs: number }
  | { readonly kind: "checklist"; readonly items: readonly string[] }

export async function executeToolWithFatigue(
  toolName: string,
  toolArgs: Readonly<Record<string, unknown>>,
  reader: AuditLogReader,
  _ctx: ChannelContext,
): Promise<ToolExecutionDecision> {
  const decision = await evaluateInlineApproval({ tool_name: toolName, args: toolArgs }, reader)
  switch (decision.action) {
    case "allow":
      return { kind: "allow" }
    case "cooldown":
      return { kind: "cooldown", durationMs: decision.duration_ms }
    case "checklist":
      return { kind: "checklist", items: decision.items }
  }
}

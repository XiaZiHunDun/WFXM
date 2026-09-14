import { computeFatigueSignal, DEFAULT_COUNT_THRESHOLD, DEFAULT_WINDOW_SECONDS } from "./signal"
import type { AuditLogReader, FatigueSignal } from "./signal"
import { matchSensitivity } from "./checklist"

export const DEFAULT_COOLDOWN_MS = 3000

export type PolicyDecision =
  | { readonly action: 'allow' }
  | { readonly action: 'cooldown'; readonly duration_ms: number; readonly signal: FatigueSignal }
  | { readonly action: 'checklist'; readonly items: readonly string[]; readonly signal: FatigueSignal }

export interface ToolCall {
  readonly tool_name: string
  readonly args: Record<string, unknown>
}

export async function evaluateInlineApproval(
  toolCall: ToolCall,
  reader: AuditLogReader,
): Promise<PolicyDecision> {
  const signal = await computeFatigueSignal(reader, DEFAULT_WINDOW_SECONDS)
  if (signal.degraded) {
    return { action: 'allow' }
  }
  const sensitivity = matchSensitivity(toolCall.tool_name)
  const isHighSignal = signal.count >= DEFAULT_COUNT_THRESHOLD

  if (sensitivity && isHighSignal) {
    // First round: cooldown; caller sleeps 3s then re-evaluates (which returns checklist)
    return { action: 'cooldown', duration_ms: DEFAULT_COOLDOWN_MS, signal }
  }
  if (sensitivity) {
    return { action: 'checklist', items: sensitivity.items, signal }
  }
  if (isHighSignal) {
    return { action: 'cooldown', duration_ms: DEFAULT_COOLDOWN_MS, signal }
  }
  return { action: 'allow' }
}

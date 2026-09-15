import { evaluateInlineApproval } from "./policy"
import type { PolicyDecision } from "./policy"
import type { AuditLogReader } from "./signal"

export interface ChannelContext {
  readonly channel: 'wechat' | 'telegram' | 'cli'
  readonly actor: string
  readonly correlationId: string
}

export interface WiringResult {
  readonly decision: PolicyDecision
  readonly proceed: () => Promise<void>
  readonly renderPrompt: () => string
}

/**
 * Shared helper for cross-channel inline-approval entry points.
 * Each channel (wechat / telegram / CLI) calls this BEFORE executing tool.
 *
 * Returns decision + proceed + renderPrompt so channel-specific UI can
 * handle cooldown wait / checklist interaction.
 */
export async function evaluateChannelApproval(
  toolName: string,
  toolArgs: Readonly<Record<string, unknown>>,
  reader: AuditLogReader,
  _ctx: ChannelContext,
): Promise<WiringResult> {
  const decision = await evaluateInlineApproval({ tool_name: toolName, args: toolArgs }, reader)

  const renderPrompt = (): string => {
    switch (decision.action) {
      case 'allow':
        return ''
      case 'cooldown':
        return `已批 ${decision.signal.count} 个，建议稍等 ${decision.duration_ms / 1000}s...`
      case 'checklist':
        return [
          '此操作 [' + toolName + '] 不可撤销，请确认：',
          ...decision.items.map((item, i) => `${i + 1}. ${item}`),
        ].join('\n')
      default:
        throw new Error(`unhandled PolicyDecision action: ${(decision as { action: string }).action}`)
    }
  }

  const proceed = async (): Promise<void> => {
    // Caller is responsible for actual tool execution; this is a no-op marker
    // that channels invoke before execution to acknowledge prompt was handled
    return Promise.resolve()
  }

  return { decision, proceed, renderPrompt }
}

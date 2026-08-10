export interface Message {
  readonly role: "user" | "assistant" | "system" | "tool"
  readonly content: string
}

export interface CompressionPlan {
  readonly compress: boolean
  readonly estimatedTokens: number
  readonly keepFirst: number
  readonly keepLast: number
  readonly reason: string
}

export interface BudgetConfig {
  readonly budgetTokens: number
  readonly charsPerToken?: number
}

const DEFAULT_CHARS_PER_TOKEN = 4

export function estimateTokens(
  messages: readonly Message[],
  charsPerToken: number = DEFAULT_CHARS_PER_TOKEN,
): number {
  let chars = 0
  for (const m of messages) chars += m.content.length
  return Math.ceil(chars / charsPerToken)
}

export function planCompression(
  messages: readonly Message[],
  config: BudgetConfig,
): CompressionPlan {
  const charsPerToken = config.charsPerToken ?? DEFAULT_CHARS_PER_TOKEN
  const tokens = estimateTokens(messages, charsPerToken)
  if (tokens <= config.budgetTokens) {
    return {
      compress: false,
      estimatedTokens: tokens,
      keepFirst: messages.length,
      keepLast: 0,
      reason: "within budget",
    }
  }

  const keepFirst = Math.floor(messages.length / 3)
  const keepLast = Math.min(
    Math.max(1, Math.ceil(messages.length / 3)),
    Math.max(0, messages.length - keepFirst - 1),
  )
  return {
    compress: true,
    estimatedTokens: tokens,
    keepFirst,
    keepLast,
    reason: `over budget (${tokens} > ${config.budgetTokens})`,
  }
}

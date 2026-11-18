export type DeepSeekThinkingType = "enabled" | "disabled"

/** True for DeepSeek V4 model ids (thinking toggle applies). */
export function isDeepSeekV4Model(model: string): boolean {
  return model.trim().toLowerCase().startsWith("deepseek-v4")
}

/**
 * Resolve thinking mode for DeepSeek V4 chat completions.
 * Returns null for legacy models (deepseek-chat, deepseek-coder, etc.).
 *
 * Default: disabled — Butler plan/intake paths need fast JSON/tool routing, not CoT.
 */
export function resolveDeepSeekThinkingType(
  env: NodeJS.ProcessEnv,
  model: string,
): DeepSeekThinkingType | null {
  if (!isDeepSeekV4Model(model)) return null
  const raw = (env["BUTLER_V5_DEEPSEEK_THINKING"] ?? "disabled").trim().toLowerCase()
  if (raw === "enabled" || raw === "1" || raw === "on" || raw === "true") {
    return "enabled"
  }
  return "disabled"
}

/** Extra JSON fields merged into DeepSeek chat/completions body. */
export function buildDeepSeekRequestExtras(
  env: NodeJS.ProcessEnv,
  model: string,
): Readonly<Record<string, unknown>> | undefined {
  const type = resolveDeepSeekThinkingType(env, model)
  if (!type) return undefined
  return { thinking: { type } }
}

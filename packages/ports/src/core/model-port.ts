/**
 * Model Port — 角色级模型选择（DESIGN §6.2 模型/记账接缝）。
 *
 * P5 Model Port 物化（D44）：让"对某角色选哪个 provider + model"成为单一真相源，
 * 被两侧消费：
 *   - `packages/adapters/src/model-router.ts`：按 ResolvedModel 构建 LLMAdapter。
 *   - `apps/api/src/llm-pricing.ts`：按同一 ResolvedModel 做模型记账 lookup
 *     （此前 `resolveCurrentLlmModel` 独立复刻选择逻辑，与执行侧 drift——MiniMax
 *     与 `BUTLER_V5_MODEL_*` 覆盖未进记账）。
 *
 * 形态是纯函数集（"实现即接口"）：Model 选择由 env 驱动、确定性、无副作用、
 * 无第二实现需求，故不建 DI 接口 + Composition Root 注入，避免休眠接口
 * （DESIGN §7 line 294）。Model Port 只承载中性 `{ provider, model }`，
 * 不承载 api-protocol 适配器面（`LLMAdapter` 仍属 `@butler/adapters`）。
 *
 * 仅依赖 TypeScript 内置类型 + `NodeJS.ProcessEnv`；0 class / 0 fetch / 0 db /
 * 0 adapters import（满足 D31 §7 thin-barrel + interface-only + 依赖方向向内）。
 */
export type ModelRole = "plan" | "exec" | "intake"

export type LlmProviderId = "anthropic" | "deepseek" | "minimax" | "dashscope"

export interface ResolvedModel {
  readonly provider: LlmProviderId
  readonly model: string
}

function envTrim(env: Readonly<NodeJS.ProcessEnv>, key: string): string {
  return (env[key] ?? "").trim()
}

/** True for DeepSeek model ids（deepseek-chat / deepseek-v4-* 等）。 */
export function isDeepSeekModelName(model: string): boolean {
  return model.trim().toLowerCase().startsWith("deepseek")
}

/**
 * 按模型名判定归属 provider。用于避免把某家的模型名发给另一家（如
 * `BUTLER_V5_MODEL_PLAN=deepseek-v4-flash` 却因为存在 MINIMAX key 而走
 * MiniMax 通道 → 400 unknown model）。未知名称返回 undefined，交回原有
 * 的「key 优先级」逻辑。
 */
function providerForModelName(model: string): LlmProviderId | undefined {
  const normalized = model.trim().toLowerCase()
  if (normalized.startsWith("deepseek")) return "deepseek"
  if (normalized.startsWith("minimax") || normalized.startsWith("abab")) return "minimax"
  return undefined
}

function hasDeepSeekKey(env: Readonly<NodeJS.ProcessEnv>): boolean {
  return envTrim(env, "DEEPSEEK_API_KEY") !== ""
}

function hasMiniMaxKey(env: Readonly<NodeJS.ProcessEnv>): boolean {
  return envTrim(env, "MINIMAX_API_KEY") !== "" || envTrim(env, "MINIMAX_CN_API_KEY") !== ""
}

function resolvePlan(env: Readonly<NodeJS.ProcessEnv>): ResolvedModel | undefined {
  if (envTrim(env, "ANTHROPIC_API_KEY")) {
    return {
      provider: "anthropic",
      model: envTrim(env, "ANTHROPIC_MODEL") || "claude-sonnet-4-20250514",
    }
  }
  // 模型名归属优先于 key 存在性：多 provider key 共存时，显式指定的模型名
  // 决定通道，避免跨家发送模型名。
  const planModel = envTrim(env, "BUTLER_V5_MODEL_PLAN")
  const planModelProvider = planModel ? providerForModelName(planModel) : undefined
  if (planModelProvider === "deepseek" && hasDeepSeekKey(env)) {
    return { provider: "deepseek", model: planModel }
  }
  if (planModelProvider === "minimax" && hasMiniMaxKey(env)) {
    return { provider: "minimax", model: planModel }
  }
  if (hasMiniMaxKey(env)) {
    // P2 fix 2026-09-04: plan role now accepts minimax (previously only
    // exec/intake did). Default model "MiniMax-M3.1-Flash" matches exec default
    // so a single key covers both roles. Owners using minimax for the
    // wechat butler loop no longer need to provision a second provider
    // key for plan.
    const model = planModel || envTrim(env, "MINIMAX_MODEL") || "MiniMax-M3.1-Flash"
    return { provider: "minimax", model }
  }
  const model = planModel || envTrim(env, "DEEPSEEK_MODEL") || "deepseek-flash"
  if (envTrim(env, "DEEPSEEK_API_KEY")) {
    return { provider: "deepseek", model }
  }
  if (envTrim(env, "DASHSCOPE_API_KEY")) {
    return { provider: "dashscope", model: "qwen-turbo" }
  }
  return undefined
}

function resolveExec(env: Readonly<NodeJS.ProcessEnv>): ResolvedModel | undefined {
  const model =
    envTrim(env, "BUTLER_V5_MODEL_EXEC") ||
    envTrim(env, "MINIMAX_MODEL") ||
    envTrim(env, "BUTLER_SMOKE_MINIMAX_MODEL") ||
    "MiniMax-M3.1-Flash"
  // BUTLER_V5_MODEL_EXEC 可能指定 deepseek 模型（如 deepseek-chat）：
  // 按模型名路由到 deepseek 通道，避免把 deepseek 模型名发给 MiniMax（400）。
  if (isDeepSeekModelName(model)) {
    if (envTrim(env, "DEEPSEEK_API_KEY")) {
      return { provider: "deepseek", model }
    }
    return resolvePlan(env)
  }
  if (envTrim(env, "MINIMAX_API_KEY") || envTrim(env, "MINIMAX_CN_API_KEY")) {
    return { provider: "minimax", model }
  }
  return resolvePlan(env)
}

function resolveIntake(env: Readonly<NodeJS.ProcessEnv>): ResolvedModel | undefined {
  const model =
    envTrim(env, "BUTLER_V5_MODEL_INTAKE") ||
    envTrim(env, "BUTLER_V5_MODEL_PLAN") ||
    envTrim(env, "DEEPSEEK_MODEL") ||
    "deepseek-flash"
  // 同 resolvePlan：模型名归属优先，避免 MiniMax 模型名被发到 DeepSeek 通道。
  const modelProvider = providerForModelName(model)
  if (modelProvider === "deepseek" && hasDeepSeekKey(env)) {
    return { provider: "deepseek", model }
  }
  if (modelProvider === "minimax" && hasMiniMaxKey(env)) {
    return { provider: "minimax", model }
  }
  if (hasDeepSeekKey(env)) {
    return { provider: "deepseek", model }
  }
  return resolvePlan(env)
}

/**
 * 按角色解析当前 provider + model（env 驱动；纯函数无副作用）。
 *
 * 模型名前缀（deepseek-* / minimax-* / abab*）优先决定 provider，其次才按
 * key 存在性回退，避免多 key 共存时把某家的模型名发给另一家（400）。
 *
 * - plan：Anthropic → 模型名归属（deepseek / minimax）→ MiniMax key → DeepSeek → DashScope。
 * - exec：deepseek-name + DEEPSEEK key→DeepSeek else MiniMax else 回退 plan。
 * - intake：模型名归属 → DeepSeek → 回退 plan。
 *
 * 返回 `undefined` 表示无任何 provider 配置（调用方回退 stub/fixture）。
 */
export function resolveModelForRole(
  env: Readonly<NodeJS.ProcessEnv>,
  role: ModelRole = "plan",
): ResolvedModel | undefined {
  switch (role) {
    case "exec":
      return resolveExec(env)
    case "intake":
      return resolveIntake(env)
    case "plan":
    default:
      return resolvePlan(env)
  }
}

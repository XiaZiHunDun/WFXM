/**
 * D61 T2 (audit #3 cluster F+G+H): owner-facing jargon filter. Replaces
 * raw internal identifiers (projectId UUIDs, env-var names, run-id hex,
 * capability names, fs paths, decision enums) with display-friendly
 * Chinese labels.
 *
 * Background: D60 T2 closed 7 owner-jargon sites (D48 §4 violations);
 * D61 audit found 14 more sites using the same pattern. The D60 fixes
 * duplicated a `catalog.find((item) => item.id === active)?.label ?? active`
 * lookup at 2 sites in `wechat-project-surface.ts` — this module centralizes
 * that and the other substitutions.
 */
import { parseWechatProjectCatalog } from "./wechat-active-project.js"

/**
 * Resolve a projectId to its owner-visible label. If the catalog has no
 * entry for the id, fall back to the raw id (better than silent `?? "?"`
 * which loses information).
 */
export function resolveProjectLabel(
  projectId: string,
  env: NodeJS.ProcessEnv,
): string {
  const catalog = parseWechatProjectCatalog(env)
  return catalog.find((item) => item.id === projectId)?.label ?? projectId
}

/**
 * Friendly short reference for a run id. `run-d2abc456-...` becomes
 * `运行 #d2abc456`. Owner can grep the full id from audit logs when needed.
 */
export function formatRunRef(runId: string): string {
  const hex = runId.replace(/^run-/, "").slice(0, 8)
  return `运行 #${hex}`
}

/**
 * Map a run-decision enum to owner-facing Chinese.
 * Mirrors `Decision.kind` literal union from `@butler/runtime/decision.ts`.
 */
export function formatDecision(decision: string): string {
  switch (decision) {
    case "Finish":
      return "完成"
    case "Respond":
      return "已回复"
    case "WaitForApproval":
      return "等待审批"
    case "WaitForTool":
      return "等待工具执行"
    case "MaxIterationsReached":
      return "已达最大迭代次数"
    case "AbortByUser":
      return "用户中止"
    case "LoopError":
      return "循环异常"
    default:
      return decision
  }
}

/**
 * D63 T2 (audit #9 F-17/F-22-F-25): owner-jargon for subagent role.
 * Drops raw English role enum from owner-facing strings. D69 T3 (audit #10
 * SO-22): complete the map (planner / tester / custom) and fall back to
 * a Chinese generic '代理' instead of leaking the raw enum string. Mirrors
 * D48 owner-jargon noted more roles than the D63 map covered.
 */
const ROLE_LABEL: Readonly<Record<string, string>> = {
  general: "通用",
  developer: "开发",
  reviewer: "审查",
  planner: "规划",
  tester: "测试",
  custom: "自定义",
}

export function formatSubagentRoleForOwner(role: string): string {
  return ROLE_LABEL[role] ?? "代理"
}

/**

/**
 * Translate a BUTLER_V5_* env-var knob name to an owner-friendly description.
 * Owner should not need to know internal env-var names — only that the
 * relevant config exists.
 */
export function describeEnvKnob(envVarName: string): string {
  // Strip prefix; map known suffixes to Chinese descriptions.
  const stripped = envVarName.replace(/^BUTLER_V5_/, "")
  const known: Readonly<Record<string, string>> = {
    CANDIDATE_EXPIRES_TTL_MS: "候选过期时长",
    SCHEDULE_ENABLED: "定时任务开关",
    TASK_RUN_ASYNC: "异步运行开关",
  }
  return known[stripped] ?? `配置项 ${stripped}`
}

/**
 * D73 T1 (audit #19 SO-001): owner-facing unauthorized 401 response.
 * Replaces 40 `c.text("unauthorized", 401)` sites across 13 owner-routes/*.ts
 * files (D72 T2 sweep missed this batch — the c.text() envelope differs
 * from the JSON `{ok:false,reason}` body that D72 swept). The body is
 * "未授权" (Chinese) so owner never sees raw English "unauthorized".
 *
 * D72 T2 sweep translated `{ok:false,reason:"..."}` JSON envelopes but
 * the c.text() 401 path is a separate Hono pattern. Centralizing here
 * so future owner-routes can call this helper directly.
 */
export function unauthorizedForOwner(c: { text: (body: string, status: number) => Response }): Response {
  return c.text("未授权", 401)
}

/**
 * D74 T1 (audit #20 SO-006): translate a domain-layer English validator
 * reason to owner-facing Chinese at the owner-route boundary. Domain
 * layer stays UI-agnostic (English-only) so its logic isn't tied to
 * owner-side wording; the owner-route wrapper converts.
 *
 * Pattern: known domain English strings → known Chinese strings. Unknown
 * strings get the caller-supplied fallback (defaults to a generic "操作
 * 失败，请稍后重试"). Mirrors D61 T1 safeOwnerError philosophy (log full,
 * return safe) but for non-error reasons (validator rejections).
 *
 * Used at 9 owner-route sites that bubble `created.reason` /
 * `parsed.reason` / `triggerCheck.reason` from packages/domain/src.
 */
const DOMAIN_REASON_TO_OWNER: Readonly<Record<string, string>> = {
  // durable-memory.ts validators
  "subject is required": "缺少 subject 参数",
  "content is required": "缺少 content 参数",
  "content exceeds 4000 chars": "内容超出长度限制（最多 4000 字）",
  "invalid sourceKind": "来源类型参数无效",
  "invalid status": "状态参数无效",
  "confidence must be between 0 and 1": "置信度参数超出范围（0-1）",
  "expiresAt must be in the future when set": "过期时间必须晚于当前时间",
  "message provenance requires messageId": "消息来源必须提供 messageId",
  "document provenance requires documentId": "文档来源必须提供 documentId",
  // document-ingest.ts validators
  "unsupported format": "不支持的文档格式",
  // task-procedure.ts validators
  "name is required": "缺少名称参数",
  "steps must be a non-empty array": "步骤列表不能为空",
  "invalid step": "步骤参数无效",
  "each step needs key, title, and goal": "每一步都需要 key / title / goal",
  "version must be >= 1": "版本号必须 >= 1",
  "goal is required": "缺少目标参数",
  "procedureStepIndex must be >= 0": "procedureStepIndex 参数必须 >= 0",
  "procedure mismatch": "流程参数不匹配",
  // project-knowledge.ts validators
  "projectId is required": "缺少 projectId 参数",
  "projectId is required for project knowledge recall": "缺少 projectId 参数",
  "title is required": "缺少标题参数",
  // project-knowledge-sources.ts validators
  "invalid JSON": "JSON 格式无效",
  "manifest must be an object": "manifest 必须是对象",
  "projects must be an object": "projects 必须是对象",
  "no valid projects in manifest": "manifest 中未配置有效项目",
  // memories.ts parseBatchIds (internal validator)
  "ids must be an array": "ids 必须是数组",
  "ids must not be empty": "ids 不能为空",
  "batch too large (max 50)": "批量数量超出限制（最多 50 个）",
  "ids must be non-empty strings": "ids 必须是非空字符串",
  // run-trigger.ts validators
  "idempotencyKey is required": "缺少 idempotencyKey 参数",
  "conversationRef is required for channel/webhook triggers":
    "channel / webhook 触发需要 conversationRef",
  // SO-003: PG error vocabulary that bubbles from batch-failed catch
  // (substring match in safeOwnerErrorString — PG prefixes the actual offending input)
  "duplicate key value violates unique constraint": "与已有记录重复",
}

/**
 * SO-003: PG error patterns that arrive as substrings inside err.message
 * (e.g. 'invalid input syntax for type uuid: "foo"'). Matched before
 * the exact-string DOMAIN_REASON_TO_OWNER lookup so PG-specific
 * vocabulary translates even when the surrounding err.message has
 * extra context. Returns the Chinese string OR null if no PG match.
 */
const PG_ERROR_SUBSTRINGS: readonly (readonly [string, string])[] = [
  ["invalid input syntax for type uuid", "未找到对应记录"],
  ["duplicate key value violates unique constraint", "与已有记录重复"],
]

const SAFE_OWNER_FALLBACK = "操作失败，请稍后重试"

export function safeOwnerErrorString(reason: string, fallback?: string): string {
  if (typeof reason !== "string") return fallback ?? SAFE_OWNER_FALLBACK
  // PG error substring match first — these come back with extra context
  // appended (e.g. the offending UUID value) so exact match would miss.
  for (const [pattern, mapped] of PG_ERROR_SUBSTRINGS) {
    if (reason.includes(pattern)) return mapped
  }
  return DOMAIN_REASON_TO_OWNER[reason] ?? fallback ?? SAFE_OWNER_FALLBACK
}

/**
 * D74 T1 (audit #20 SO-007): allowlist for `subject` field in audit
 * emit. Body.subject comes from HTTP request body (attacker-controllable
 * until bearer auth lands in D74+). Reject anything outside the
 * allowlist at the boundary, defaulting to "owner" — prevents audit
 * `subject` column forgery via crafted owner HTTP request.
 *
 * Mirrors the actor sentinel pattern (D73 T4 SO-011): audit emit
 * hardens "who can write this column" with an explicit allowlist rather
 * than trusting request body. 9 owner-route sites apply this check.
 */
export const ALLOWED_SUBJECTS: ReadonlySet<string> = new Set([
  "owner",
  "assistant",
  "system",
])

export function isAllowedSubject(s: unknown): s is "owner" | "assistant" | "system" {
  return typeof s === "string" && ALLOWED_SUBJECTS.has(s)
}

/**
 * D74 T1 (audit #20 SO-002 + SO-029): translate a Telegram API failure
 * reason to owner-facing Chinese. Telegram's English description
 * ('Bad Request: chat not found', 'Forbidden: bot was blocked by the
 * user') and our own English-fallback templates
 * ('telegram API HTTP ${status}', 'telegram API timeout after ${ms}ms',
 * raw err.message) all leak operator vocabulary to owner's delivery
 * audit. Map known shapes; unknown strings pass through
 * safeOwnerErrorString for last-resort translation.
 */
export function mapChannelErrorToOwnerJargon(reason: string): string {
  if (typeof reason !== "string") return "Telegram 接口调用失败"
  // Pre-existing English fallback templates we wrote ourselves.
  const httpMatch = /^telegram API HTTP (\d+)$/.exec(reason)
  if (httpMatch) return `Telegram 接口返回错误（状态 ${httpMatch[1]}）`
  const timeoutMatch = /^telegram API timeout after (\d+)ms$/.exec(reason)
  if (timeoutMatch) return `Telegram 接口响应超时（${timeoutMatch[1]} 毫秒）`
  // Upstream Telegram API description — translate the common patterns.
  if (/^Bad Request: chat not found$/i.test(reason)) return "对话不存在或无法访问"
  if (/^Forbidden: bot was blocked by the user$/i.test(reason)) return "用户已屏蔽此机器人"
  if (/^Bad Request: message is not modified$/i.test(reason)) return "消息内容未变化"
  if (/^Too Many Requests/i.test(reason)) return "调用频率过高，请稍后重试"
  // Fallback: keep raw English out of owner surface.
  return safeOwnerErrorString(reason, "Telegram 接口调用失败")
}

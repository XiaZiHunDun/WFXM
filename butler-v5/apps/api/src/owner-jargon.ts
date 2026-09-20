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

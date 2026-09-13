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
 * Render an absolute filesystem path as a workspace-relative display path
 * for owner-facing replies. Falls back to `path` if it cannot be made
 * relative (path outside workspace root).
 */
export function publicPath(absolutePath: string, workspaceRoot: string): string {
  if (workspaceRoot && absolutePath.startsWith(workspaceRoot + "/")) {
    return absolutePath.slice(workspaceRoot.length + 1)
  }
  return absolutePath
}

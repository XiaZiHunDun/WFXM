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
 * D63 T2 (audit #9 F-01): owner-jargon for the approval question.
 * Replaces the English template (`Confirm ${capability} on ${resource}?`)
 * that flowed from capability-boundary.ts:285 into owner WeChat replies.
 * Maps raw capability names to Chinese; keeps resource path verbatim
 * (caller can wrap with publicPath() if workspace-root stripping is wanted).
 */
const CAPABILITY_LABEL: Record<string, string> = {
  write_file: "写入文件",
  run_command: "运行命令",
  send_wechat_file: "发送文件",
  delegate_to_subagent: "委派子代理",
  read_file: "读取文件",
  summarize_today: "汇总今日",
  recall_history: "调用历史",
  get_current_time: "查询时间",
}

export function formatApprovalQuestionForOwner(
  capability: string,
  resource: string,
): string {
  const label = CAPABILITY_LABEL[capability] ?? "执行操作"
  return `是否${label}（${resource}）？`
}

/**
 * D63 T2 (audit #9 F-17/F-22-F-25): owner-jargon for subagent role.
 * Drops raw English role enum (`general`, `developer`, `reviewer`) from
 * owner-facing strings. Falls back to a Chinese generic if the role
 * isn't in the known map.
 */
const ROLE_LABEL: Record<string, string> = {
  general: "通用",
  developer: "开发",
  reviewer: "审查",
}

export function formatSubagentRoleForOwner(role: string): string {
  return ROLE_LABEL[role] ?? role
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

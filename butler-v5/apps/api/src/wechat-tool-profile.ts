/** Shared WeChat tool surface: plan (read-only) vs exec (write/command). */
import { WEIBUTLER_LLM_TOOLS } from "./tools.js"
import { envTruthy } from "./env-util.js"
import { isSubagentEnabled } from "./subagent-config.js"

export type WechatIntakeIntentKind =
  | "chat"
  | "dev_task"
  | "dev_session"
  | "switch_project"
  | "continue_dev"

export const EXEC_TOOL_NAMES = ["run_command", "write_file"] as const

export function allWechatCoreToolNames(env: NodeJS.ProcessEnv = process.env): readonly string[] {
  const names = WEIBUTLER_LLM_TOOLS.map((t) => t.name)
  if (isSubagentEnabled(env)) return names
  return names.filter((n) => n !== "delegate_to_subagent")
}

/** Opt-in legacy: main Loop direct write/run (scheme B default is Child Run only). */
export function isDevDirectExecEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return envTruthy(env["BUTLER_V5_DEV_DIRECT_EXEC"])
}

export function isDevWorkIntent(kind: WechatIntakeIntentKind): boolean {
  return kind === "dev_task" || kind === "continue_dev"
}

/**
 * Scheme B (default): dev_task → plan + delegate, no exec on main Loop.
 * Legacy: BUTLER_V5_DEV_DIRECT_EXEC=1 → exec on main Loop, hide delegate.
 */
export function resolveToolNamesForIntake(args: {
  readonly intentKind: WechatIntakeIntentKind
  readonly baseAllowlist?: readonly string[]
  readonly env?: NodeJS.ProcessEnv
}): readonly string[] {
  const env = args.env ?? process.env
  const base = args.baseAllowlist ?? allWechatCoreToolNames(env)
  const execSet = new Set<string>(EXEC_TOOL_NAMES)
  const devWork = isDevWorkIntent(args.intentKind)
  const directExec = devWork && isDevDirectExecEnabled(env)

  if (directExec) {
    let names: readonly string[] = base
    if (isSubagentEnabled(env)) {
      names = names.filter((name) => name !== "delegate_to_subagent")
    }
    return names
  }

  let names = base.filter((name) => !execSet.has(name))
  if (devWork && isSubagentEnabled(env) && !names.includes("delegate_to_subagent")) {
    names = [...names, "delegate_to_subagent"]
  }
  return names
}

export function shouldAdvertiseDelegate(args: {
  readonly includeExecTools: boolean
  readonly env?: NodeJS.ProcessEnv
}): boolean {
  const env = args.env ?? process.env
  if (!isSubagentEnabled(env)) return false
  if (args.includeExecTools) return false
  return true
}

export function isExecCapability(name: string): boolean {
  return (EXEC_TOOL_NAMES as readonly string[]).includes(name)
}

export function toolSurfaceMatchesCorpus(args: {
  readonly intentKind: WechatIntakeIntentKind
  readonly allowedToolNames: readonly string[]
  readonly expectToolSurface: string
  readonly env?: NodeJS.ProcessEnv
}): boolean {
  const hasExec = args.allowedToolNames.some((n) => isExecCapability(n))
  const hasDelegate = args.allowedToolNames.includes("delegate_to_subagent")
  switch (args.expectToolSurface) {
    case "plan":
      return !hasExec
    case "plan+delegate":
      return !hasExec && hasDelegate
    default:
      return false
  }
}

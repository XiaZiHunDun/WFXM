/** Core (non-MCP) tools exposed on the WeChat butler loop by default. */
export const WECHAT_CORE_TOOL_NAMES: readonly string[] = [
  "recall_history",
  "recall_durable_memory",
  "recall_document",
  "recall_project_knowledge",
  "get_current_time",
  "greet_with_time",
  "summarize_today",
  "read_file",
  "write_file",
  "run_command",
  "send_wechat_file",
]

export const WECHAT_SUBAGENT_TOOL_NAME = "delegate_to_subagent" as const

export type WechatProjectToolAllowlist = {
  readonly mcpTools: readonly string[] | "*"
}

export type WechatToolAllowlistConfig = {
  readonly version: number
  readonly default?: WechatProjectToolAllowlist
  readonly projects?: Readonly<Record<string, WechatProjectToolAllowlist>>
}

/**
 * Merge core WeChat tools with project-scoped MCP capabilities.
 * When `mcpTools` is `"*"`, every name in `availableMcpCapabilities` is included.
 */
export function buildWechatAllowedToolNames(input: {
  readonly config: WechatToolAllowlistConfig
  readonly projectId: string
  readonly availableMcpCapabilities: readonly string[]
  readonly includeSubagent?: boolean
}): readonly string[] {
  const projectKey = input.projectId.trim()
  const projectEntry =
    (projectKey.length > 0 ? input.config.projects?.[projectKey] : undefined) ??
    input.config.default ??
    { mcpTools: [] as readonly string[] }
  const core = input.includeSubagent
    ? [...WECHAT_CORE_TOOL_NAMES, WECHAT_SUBAGENT_TOOL_NAME]
    : [...WECHAT_CORE_TOOL_NAMES]
  const available = new Set(input.availableMcpCapabilities)
  const mcpNames =
    projectEntry.mcpTools === "*"
      ? input.availableMcpCapabilities.filter((name) => available.has(name))
      : projectEntry.mcpTools.filter((name) => available.has(name))
  return [...core, ...mcpNames]
}

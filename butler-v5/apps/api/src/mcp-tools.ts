import type { LLMTool } from "@butler/adapters"
import type { ToolDefinition } from "@butler/runtime/tool-runtime.js"
import {
  isMcpEnabled,
  mcpStubToolNames,
  toMcpCapabilityName,
  toMcpCapabilityNameForServer,
} from "@butler/runtime/mcp-gate.js"

export interface McpDiscoveredTool {
  readonly name: string
  readonly description?: string
  readonly inputSchema?: Readonly<Record<string, unknown>>
}

export type McpInvokeFn = (
  toolName: string,
  args: Readonly<Record<string, unknown>>,
) => Promise<{ readonly ok: true; readonly output: unknown } | { readonly ok: false; readonly reason: string }>

export interface McpToolsOptions {
  readonly discovered?: readonly McpDiscoveredTool[]
  readonly invoke?: McpInvokeFn
}

function defaultInvoke(toolName: string): McpInvokeFn {
  return async (_name, _args) => ({
    ok: false,
    reason: `MCP tool ${toolName} has no invoke handler (configure BUTLER_V5_MCP_URL or inject invoke)`,
  })
}

export interface McpToolsOptions {
  readonly discovered?: readonly McpDiscoveredTool[]
  readonly invoke?: McpInvokeFn
  readonly serverId?: string
  readonly namespaced?: boolean
}

export function makeMcpToolDefinition(
  discovered: McpDiscoveredTool,
  invoke: McpInvokeFn = defaultInvoke(discovered.name),
  options: { readonly serverId?: string; readonly namespaced?: boolean } = {},
): ToolDefinition {
  const capability =
    options.namespaced && options.serverId
      ? toMcpCapabilityNameForServer(options.serverId, discovered.name)
      : toMcpCapabilityName(discovered.name)
  if (!capability) {
    throw new Error(`invalid MCP tool name: ${discovered.name}`)
  }
  return {
    name: capability as ToolDefinition["name"],
    risk: "high",
    async run(args: Record<string, unknown>) {
      return invoke(discovered.name, args)
    },
  }
}

export function mcpLlmToolDescriptor(
  discovered: McpDiscoveredTool,
  options: { readonly serverId?: string; readonly namespaced?: boolean } = {},
): LLMTool {
  const name =
    options.namespaced && options.serverId
      ? toMcpCapabilityNameForServer(options.serverId, discovered.name)
      : toMcpCapabilityName(discovered.name)
  if (!name) {
    throw new Error(`invalid MCP tool name: ${discovered.name}`)
  }
  return {
    name,
    description:
      discovered.description?.trim() ||
      `MCP tool (${discovered.name}). Requires owner approval before execution.`,
    parameters: discovered.inputSchema ?? { type: "object", properties: {} },
  }
}

/**
 * Load MCP ToolDefinitions when opt-in is enabled. Without a live server,
 * `BUTLER_V5_MCP_TOOL_NAMES=foo,bar` registers stub descriptors for wiring tests.
 */
export function loadMcpToolDefinitions(
  env: NodeJS.ProcessEnv = process.env,
  options: McpToolsOptions = {},
): readonly ToolDefinition[] {
  if (!isMcpEnabled(env)) return []
  const discovered =
    options.discovered ??
    mcpStubToolNames(env).map((name) => ({ name, description: `MCP stub: ${name}` }))
  const invoke = options.invoke
  const toolOptions = {
    ...(options.serverId ? { serverId: options.serverId } : {}),
    ...(options.namespaced ? { namespaced: options.namespaced } : {}),
  }
  return discovered.map((tool) =>
    makeMcpToolDefinition(tool, invoke ?? defaultInvoke(tool.name), toolOptions),
  )
}

export function loadMcpLlmTools(
  env: NodeJS.ProcessEnv = process.env,
  options: McpToolsOptions = {},
): readonly LLMTool[] {
  if (!isMcpEnabled(env)) return []
  const discovered =
    options.discovered ??
    mcpStubToolNames(env).map((name) => ({ name, description: `MCP stub: ${name}` }))
  return discovered.map((tool) => mcpLlmToolDescriptor(tool, {
    ...(options.serverId ? { serverId: options.serverId } : {}),
    ...(options.namespaced ? { namespaced: options.namespaced } : {}),
  }))
}

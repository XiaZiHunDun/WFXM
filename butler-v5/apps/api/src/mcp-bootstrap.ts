import type { LLMTool } from "@butler/adapters"
import { makeMcpClientAdapter } from "@butler/adapters/mcp/client.js"
import { makeMcpHttpTransport } from "@butler/adapters/mcp/http-transport.js"
import type { ToolDefinition } from "@butler/runtime/tool-runtime.js"
import { isMcpEnabled } from "@butler/runtime/mcp-gate.js"
import {
  loadMcpLlmTools,
  loadMcpToolDefinitions,
  mcpLlmToolDescriptor,
  type McpDiscoveredTool,
  type McpInvokeFn,
} from "./mcp-tools.js"
import { mcpFailClosedOnBootstrap, mcpUsesStubTools, parseMcpServerConfig } from "./mcp-config.js"

export interface McpToolBundle {
  readonly runtimeTools: readonly ToolDefinition[]
  readonly llmTools: readonly LLMTool[]
  readonly mode: "off" | "stub" | "http"
  readonly discovered: readonly McpDiscoveredTool[]
}

const EMPTY_BUNDLE: McpToolBundle = {
  runtimeTools: [],
  llmTools: [],
  mode: "off",
  discovered: [],
}

export async function bootstrapMcpTools(
  env: NodeJS.ProcessEnv = process.env,
  options: {
    readonly fetch?: typeof fetch
    readonly discover?: () => Promise<readonly McpDiscoveredTool[]>
    readonly invoke?: McpInvokeFn
  } = {},
): Promise<McpToolBundle> {
  if (!isMcpEnabled(env)) {
    return EMPTY_BUNDLE
  }

  if (mcpUsesStubTools(env)) {
    const discovered = mcpStubDiscovered(env)
    const invoke = options.invoke
    return {
      mode: "stub",
      discovered,
      runtimeTools: loadMcpToolDefinitions(env, { discovered, ...(invoke ? { invoke } : {}) }),
      llmTools: loadMcpLlmTools(env, { discovered }),
    }
  }

  const server = parseMcpServerConfig(env)
  if (!server.ok) {
    if (mcpFailClosedOnBootstrap(env)) {
      throw new Error(`MCP bootstrap failed: ${server.reason}`)
    }
    return EMPTY_BUNDLE
  }

  try {
    const headers: Record<string, string> = {}
    if (server.value.token) {
      headers["authorization"] = `Bearer ${server.value.token}`
    }
    const transport = makeMcpHttpTransport({
      url: server.value.url,
      timeoutMs: server.value.timeoutMs,
      headers,
      ...(options.fetch ? { fetch: options.fetch } : {}),
    })
    const client = makeMcpClientAdapter({ transport })
    const discovered = options.discover
      ? await options.discover()
      : (await client.discover()).map((tool) => ({
          name: tool.name,
          description: tool.description,
          inputSchema: tool.inputSchema,
        }))
    const invoke: McpInvokeFn =
      options.invoke ??
      (async (toolName, args) => {
        const result = await client.invoke(toolName, args)
        if (!result.ok) {
          return { ok: false, reason: result.reason ?? "MCP invoke failed" }
        }
        return { ok: true, output: result.output }
      })
    return {
      mode: "http",
      discovered,
      runtimeTools: loadMcpToolDefinitions(env, { discovered, invoke }),
      llmTools: discovered.map((tool) => mcpLlmToolDescriptor(tool)),
    }
  } catch (err) {
    const reason = err instanceof Error ? err.message : String(err)
    if (mcpFailClosedOnBootstrap(env)) {
      throw new Error(`MCP bootstrap failed: ${reason}`)
    }
    return EMPTY_BUNDLE
  }
}

function mcpStubDiscovered(env: NodeJS.ProcessEnv): readonly McpDiscoveredTool[] {
  const raw = (env["BUTLER_V5_MCP_TOOL_NAMES"] ?? "").trim()
  if (!raw) return []
  return raw
    .split(/[,\s]+/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0)
    .map((name) => ({ name, description: `MCP stub: ${name}` }))
}
